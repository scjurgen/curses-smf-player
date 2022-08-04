#!/usr/bin/env python3

"""
TODO (JS):
 - add transpose, octave
 - define out port name
 - add time code start point (h,m,s,f)
 - auto loop mode
"""

import argparse
import rtmidi
import sys
import time
from threading import Thread, Event
from mido import MidiFile, Message, tempo2bpm, merge_tracks, tick2second, second2tick


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    arg = parser.add_argument

    # arg('-p', '--virtual-port', help='Mido port name to send output to (midi-curse)')
    # arg('-c', '--clock', dest='midi_clock', action='store_true', default=False, help='Send midi clock messages')
    arg('-t', '--timecode', dest='midi_timecode', action='store_true', default=False, help='Send midi time_code')
    arg('-l', '--loop', dest='loop', action='store_true', default=False, help='loop loop ')
    arg('-q', '--quiet', dest='quiet', action='store_true', default=False, help='print nothing')
    arg('files', metavar='FILE', nargs='+', help='MIDI file to play')
    return parser.parse_args()


'''
clock 0xF8 (24 per beat)
start 0xFA
continue 0xFB
stop 0xFC
active sense
'''
'''
Byte 0
0rrhhhhh: Rate (0–3) and hour (0–23).
rr = 00: 24 frames/s
rr = 01: 25 frames/s
rr = 10:  29.97 frames/s (SMPTE drop-frame timecode)
rr = 11: 30 frames/s
Byte 1
00mmmmmm: Minute (0–59)
Byte 2
00ssssss: Second (0–59)
Byte 3
000fffff: Frame (0–29, or less at lower frame rates)


0	0000 ffff	Frame number lsbits
1	0001 000f	Frame number msbit
2	0010 ssss	Second lsbits
3	0011 00ss	Second msbits
4	0100 mmmm	Minute lsbits
5	0101 00mm	Minute msbits
6	0110 hhhh	Hour lsbits
7	0111 0rrh	Rate and hour msbit'''


class miditimecode:
    def __init__(self, output):
        self.midi_out = output
        self.reset()
        #self.flog = open("/tmp/mtc.log", "w")

    def reset(self):
        self.sendMTC = True
        self.framesSinceReset = 0
        self.framesPerSec = 24
        self.subframe = 0
        self.h = 1
        self.m = 0
        self.s = 0
        self.f = 0
        self.ft = 0
        if self.framesPerSec == 24:
            self.rr = 0b00000000
        elif self.framesPerSec == 25:
            self.rr = 0b00100000
        elif self.framesPerSec == 29.97:
            self.rr = 0b01000000
        elif self.framesPerSec == 30:
            self.rr = 0b01100000

    def setSendMTC(self, value:bool):
        self.sendMTC = value

    def start(self):
        self.reset()
        if self.sendMTC:
            msgTimeCode = Message('sysex', data=[0x7F, 0x7F, 0x01, 0x01, self.rr + self.h, self.m, self.s, self.f])
            self.midi_out.send_message(msgTimeCode.bytes())
        self.start_time = time.time()
        self.framesSinceReset = 0
        self.next_time = self.start_time

    def writeTolog(self, comment):
        self.flog.write(f"{comment} {time.time() - self.next_time} {self.__str__()}\n")

    def next(self):
        if time.time() < self.next_time:
            return
        self.subframe += 1
        if self.subframe == 4:
            self.subframe = 0
            self.f += 1
            if self.f >= self.framesPerSec:
                self.f = 0
                self.s += 1
                if self.s >= 60:
                    self.s = 0
                    self.m += 1
                    if self.m >= 60:
                        self.m = 0
                        self.h += 1
            # self.writeTolog(f"{time.time() - self.start_time}")
        if self.sendMTC:
            if self.ft == 0:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=self.f & 0xf)
            elif self.ft == 1:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=(self.f & 0x10) >> 4)
            elif self.ft == 2:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=self.s & 0xf)
            elif self.ft == 3:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=(self.s & 0x30) >> 4)
            elif self.ft == 4:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=self.m & 0xf)
            elif self.ft == 5:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=(self.m & 0x30) >> 4)
            elif self.ft == 6:
                quarterFrame = Message('quarter_frame', frame_type=self.ft, frame_value=self.h & 0xf)
            elif self.ft == 7:
                quarterFrame = Message('quarter_frame', frame_type=self.ft,
                                       frame_value=(self.h & 0x10) >> 4 | (self.rr << 1))
            self.ft += 1
            if self.ft >= 8:
                self.ft = 0
            b = quarterFrame.bytes()
            self.midi_out.send_message(b)
        self.framesSinceReset += 1
        self.next_time = self.start_time + self.framesSinceReset * 1 / self.framesPerSec / 4

    def __str__(self):
        return f"{self.h:2}:{self.m:02}:{self.s:02}:{self.f:02}"

    def currentValues(self):
        return {"hour": self.h, "min": self.m, "sec": self.s, "frame": self.f, "rate": self.framesPerSec}


class smfplayout:
    def __init__(self, output):
        self.midi_out = output
        self.mtc = miditimecode(output)
        self.sendMTC = True
        self.loop = 1
        self.playing = False

    def dataInfo(self):
        infoDict = {"playing": self.playing, "beat": self.beat+1, "bar": self.bar+1, "key": self.keysignature,
                    "signature": [self.numerator, self.denominator], "tempo": self.tempo, "lengthSeconds": self.midi_data.length}
        infoDict["mtc"] = self.mtc.currentValues()
        return infoDict

    def setSendMTC(self, value:bool):
        self.sendMTC = value
        self.mtc.setSendMTC(value)

    def restart(self):
        self.current_time = 0.0
        self.tempo = 500000
        self.numerator = 4
        self.denominator = 4
        self.beat = 0
        self.bar = 0
        self.barAdd = 0
        self.currentTick = 0
        self.keysignature = ""
        self.nextClockTick = 0
        self.newTranspose = None
        self.mtc.reset()

    def barbeatFromTicks(self, tick):
        beat = tick / self.midi_data.ticks_per_beat * self.denominator / 4
        self.bar = int(beat / self.numerator)
        self.beat = int(beat % self.numerator)

    def setTranspose(self, newTranspose:int):
        self.newTranspose = newTranspose

    def stopPendingNotes(self):
        for c in range(16):
            msg = Message('control_change', channel=c, control=64, value=0)
            self.midi_out.send_message(msg.bytes())
            msg = Message('control_change', channel=c, control=66, value=0)
            self.midi_out.send_message(msg.bytes())
            msg = Message('control_change', channel=c, control=121, value=0)
            self.midi_out.send_message(msg.bytes())
            for n in range(128):
                while self.pendingNotes[c][n] > 0:
                    msg = Message('note_off', channel=c, note=n, velocity=0x40)
                    self.midi_out.send_message(msg.bytes())
                    self.pendingNotes[c][n] -= 1

    def play_out(self, midi_data, eventStop: Event, updateMessage, loopCnt:int, transpose:int):
        self.loop = loopCnt
        self.restart()
        self.midi_data = midi_data
        self.mt = merge_tracks(midi_data.tracks)
        self.mtc.start()
        self.pendingNotes = []
        for c in range(16):
            self.pendingNotes.append( [0] * 128)
        self.playing = True
        self.newTranspose = None
        for i in range(self.loop):
            if eventStop.isSet():
                break
            ms = 0
            mfIndex = 0
            tick = 0
            msg = self.mt[mfIndex]
            #msg.time += self.midi_data.ticks_per_beat * 4
            nextMsecItem = 1000 * tick2second(msg.time, self.midi_data.ticks_per_beat, self.tempo)
            #print(nextMsecItem)
            self.start_time = time.time()

            self.nextUpdate = 0
            while mfIndex < len(self.mt):
                if eventStop.isSet():
                    break
                time.sleep(0.0001)
                delta = (time.time() - self.start_time) * 1000
                if delta > ms:
                    self.mtc.next()
                    lastBeat = self.beat
                    virtualTick = second2tick(delta / 1000, self.midi_data.ticks_per_beat, self.tempo)
                    self.barbeatFromTicks(virtualTick)
                    if ms > self.nextUpdate:
                        updateMessage(self.dataInfo())
                        self.nextUpdate = ms+100
                        if self.newTranspose is not None:
                            transpose = self.newTranspose
                            self.stopPendingNotes()
                            self.newTranspose = None
                    ms += 1

                    # self.mtc.writeTolog(f"{str(ms)} {nextMsecItem}:")
                    if ms >= nextMsecItem:
                        if msg.type == 'set_tempo':
                            self.tempo = msg.tempo
                            self.bpm = tempo2bpm(msg.tempo)
                            # reset time for new BPM
                            self.barbeatFromTicks(tick)
                            self.barAdd = self.bar
                            tick = 0
                            self.start_time = time.time()
                            ms = 0

                        elif msg.type == 'time_signature':
                            self.numerator = msg.numerator
                            self.denominator = msg.denominator
                        elif msg.type == 'key_signature':
                            self.keysignature = msg.key

                        if isinstance(msg, Message):
                            if msg.type == 'note_on':
                                if transpose != 0:
                                    msg.note += transpose
                                self.pendingNotes[msg.channel][msg.note] += 1
                            else:
                                if msg.type == 'note_off':
                                    if transpose != 0:
                                        msg.note += transpose
                                    self.pendingNotes[msg.channel][msg.note] -= 1
                            self.midi_out.send_message(msg.bytes())

                        mfIndex += 1
                        if mfIndex < len(self.mt):
                            msg = self.mt[mfIndex]
                            tick += msg.time
                            nextMsecItem = 1000 * tick2second(tick, self.midi_data.ticks_per_beat, self.tempo)

                self.currentTick += msg.time
        for c in range(16):
            for n in range(128):
                if self.pendingNotes[c][n] > 0:
                    msg = Message('note_off', channel=c, note=n, velocity=0x40)
                    self.midi_out.send_message(msg.bytes())
        self.playing = False
        updateMessage(self.dataInfo())
        self.stopAll()

    def play_file(self, filename: str, eventStop: Event, updateMessage, loopcnt:int, transpose:int):
        midi_data = MidiFile(filename)
        self.play_out(midi_data, eventStop, updateMessage, loopcnt, transpose)

    def stopAll(self):
        for i in range(16):
            self.midi_out.send_message([0xB0 + i, 7, 0x80])
            self.midi_out.send_message([0xB0 + i, 120, 0])
            self.midi_out.send_message([0xB0 + i, 121, 0])
            self.midi_out.send_message([0xB0 + i, 123, 0])
            self.midi_out.send_message([0xB0 + i, 127, 0])

def quiet(m:dict):
    pass

def main():
    try:
        midiout = rtmidi.MidiOut()
        midiout.open_virtual_port("midi-curse")
        smfPlayer = smfplayout(midiout)
        e = Event()
        time.sleep(1)

        for filename in args.files:
            if args.loop:
                loopcnt = 99999
            else:
                loopcnt = 1
            if args.quiet:
                smfPlayer.play_file(filename, e, quiet, loopcnt, 0)
            else:
                smfPlayer.play_file(filename, e, print, loopcnt, 0)
        del midiout

    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    args = parse_args()

    if args.quiet:
        def print(*args):
            pass
    main()
