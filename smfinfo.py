#!/usr/bin/env python3

import sys
from mido import MidiFile, Message, tempo2bpm, merge_tracks, tick2second, second2tick


def get_tempo(track):
    for msg in track:
        if msg.type == 'set_tempo':
            return msg.tempo
    return 500000

def showInfo(filename:str):

    midi_data = MidiFile(filename)

    tpqn = midi_data.ticks_per_beat
    tempo = get_tempo(midi_data.tracks[0])

    print(f"{filename}:")
    print(f"    tpqn: {tpqn}")
    print(f"    tempo: {tempo} {round(10*tempo2bpm(tempo))/10} BPM")

for i in range(1, len(sys.argv)):
    showInfo(sys.argv[i])
