#!/usr/bin/env python3

import curses

from curses import wrapper
import json
import os

import rtmidi
from pathlib import Path

import time


class Settings:

    def __init__(self):
        self.home = str(Path.home())
        self.homedir = f"{self.home}/.curseskeyplay/"
        if not os.path.isdir(self.homedir):
            os.mkdir(self.homedir, 0o700)
        self.settingsFileName = f"{self.homedir}settings.json"
        try:
            with open(self.settingsFileName, "r") as f:
                data = f.read()
                self.jsonData = json.loads(data)
        except:
            self.jsonData = {"home": self.home, "lastworkingdirectory": os.getcwd(), "arpeggiator": False}
            self.createSettingsFile()

    def setCurrentWorkingDirectory(self, path:str):
        self.jsonData["lastworkingdirectory"] = path
        self.createSettingsFile()

    def createSettingsFile(self):
        with open(self.settingsFileName, "w") as f:
            s = json.dumps(self.jsonData)
            f.write(s)


class App:
    def __init__(self):
        self.screen = curses.initscr()
        self.screen.keypad(True)
        curses.noecho()
        self.screen.nodelay(True)
        curses.cbreak()
        curses.curs_set(0)
        curses.use_default_colors()
        for i in range(8):
            curses.init_pair(i, i, -1)
        for i in range(8):
            curses.init_pair(i + 8, 0, i)
        self.infow = 30
        self.indexfile = 0
        self.topindex = 0
        self.rows, self.cols = self.screen.getmaxyx()
        self.rows -= 2
        self.wdir = self.cols - self.infow

        self.transpose = 0
        self.baseNote = 48
        self.velocity = 120
        self.resetScreen()
        self.activeNotes = {}
        self.notesOffCounter = 0


    def handleNoteOn(self, h: int):
        if h in self.activeNotes:
            del self.activeNotes[h]
            self.midi_out.send_message([0x80, self.baseNote + h, 64])
            self.screen.addstr(2, h, f'-')
        else:
            self.notesOffCounter = 100000
            self.midi_out.send_message([0x90, self.baseNote + h, self.velocity])
            self.activeNotes[h] = self.velocity
            self.screen.addstr(2, h, f'O')

    def tickAutoNotesOff(self):
        if self.notesOffCounter > 0:
            self.notesOffCounter -= 1
            if self.notesOffCounter == 0:
                for key, value in self.activeNotes.items():
                    self.midi_out.send_message([0x80, self.baseNote + key, 64])

    def sendNote(self, k: str):
        notemap = {
            'a': 0,
            'w': 1,
            's': 2,
            'e': 3,
            'd': 4,
            'f': 5,
            't': 6,
            'g': 7,
            'y': 8,
            'h': 9,
            'u': 10,
            'j': 11,
            'k': 12,
            'o': 13,
            'l': 14,
            'p': 15,
            ';': 16,
            '\'': 17
        }
        if k in notemap:
            h = notemap[k]
            self.handleNoteOn(h)

    def resetScreen(self):
        self.rows, self.cols = self.screen.getmaxyx()
        self.wdir = self.cols - self.infow
        self.rows -= 2

    def interpretKey(self, key):
        #self.screen.addstr(self.rows + 1, 0, f'{key}          ')
        #self.screen.refresh()

        if 'KEY_UP' == key:
            pass
        elif 'KEY_DOWN' == key:
            pass
        elif key in ['+']:
            pass
        elif key in ['-']:
            pass
        elif key in ['\x1b']:
            return False
        elif key in "asdfghjkl;'wetyuop":
            self.sendNote(key)
        self.screen.move(1, self.wdir + self.rows - 2)
        self.screen.addstr(1, 2, f" {key} {ord(key)}     ")
        return True

    def cleanExit(self):
        curses.nocbreak()
        self.screen.keypad(False)
        curses.echo()
        curses.endwin()

    def loadSettings(self):
        self.settings = Settings()
        try:
            os.chdir(self.settings.jsonData["lastworkingdirectory"])
        except:
            print("couldn't go to last directory")
            self.settings.setCurrentWorkingDirectory(os.getcwd())

    def run(self) -> bool:

        self.midi_out = rtmidi.MidiOut()
        self.midi_out.open_virtual_port("midi-curse")
        #index = 0
        while True:
            self.tickAutoNotesOff()
            #index += 1
            #self.screen.addstr(4, 2, f" {index}     ")
            try:
                time.sleep(0.001)
                key = self.screen.getkey()
                if key != -1:
                    if key == 'KEY_RESIZE':
                        self.cleanExit()
                        return True
                    elif not self.interpretKey(key):
                        self.cleanExit()
                        print("bBck to shell...")
                        return False

            except Exception as e:
                #print("Exception raised:", e)
                time.sleep(0.001)

def main(cursesWindow):
    app = App()
    while(app.run()):
        time.sleep(0.05)
        app = App()

if __name__ == '__main__':
    wrapper(main)

