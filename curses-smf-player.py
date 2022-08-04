#!/usr/bin/env python3

import curses

from curses import wrapper
import json
import os
import re
import rtmidi
from pathlib import Path
from threading import Thread, Event
import time
from mido import MidiFile
from smfplayout import smfplayout

flog = open("/tmp/player.log", "w")

class MidifileSet:
    def __init__(self):
        self.cwd = os.getcwd()
        self.midifiles = list()

    def changedir(self, newdir:str):
        os.chdir(newdir)

    def scanDir(self):
        self.cwd = os.getcwd()
        self.midifiles = list()
        regex = re.compile(".*\.(midi?|kar)$")
        sdir = os.listdir(self.cwd)
        sdir.sort()
        for file in sdir:
            if os.path.isdir(file):
                if file[0] != '.':
                    self.midifiles.append([file,'dir'])
        for file in sdir:
            if os.path.isfile(file):
                if regex.match(file):
                    self.midifiles.append([file, 'file'])

    def fetch(self):
        return self.midifiles


class InfoScreen:
    def __init__(self, wh):
        self.wh = wh
        self.bpm = 120
        self.mtc = True
        self.bar = 0
        self.beat = 0
        self.numerator = 4
        self.denominator = 4
        self.key = "-"
        self.h = 1
        self.m = 0
        self.s = 0
        self.f = 0
        self.rate = 24
        self.lenSeconds = 0
        self.loop = False
        self.playing = False
        self.transpose = 0
        self.hasNewValues = False

    def showValues(self):
        self.hasNewValues = False
        if self.playing:
            self.wh.addnstr(1, 1, "PLAYING", self.cols, curses.color_pair(2) | curses.A_BOLD)
            self.wh.addnstr(4, 1, f"Pos: ", self.cols)
            self.wh.addnstr(4, 6, f"{self.bar}.{self.beat}    ", self.cols, curses.color_pair(2) | curses.A_BOLD)
        else:
            self.wh.addnstr(1, 1, "STOPPED", self.cols, curses.color_pair(5))
            self.wh.addnstr(4, 1, f"Pos: {self.bar}.{self.beat}    ", self.cols)
        self.wh.addnstr(3, 1, f"Bpm: {self.bpm}      ", self.cols)
        self.wh.addnstr(5, 1, f"Len: {int(self.lenSeconds / 60):02}'{int(self.lenSeconds) % 60:02}''     ", self.cols)
        self.wh.addnstr(6, 1, f"Key: {self.key}      ", self.cols)
        self.wh.addnstr(7, 1, f"Sig: {self.numerator}/{self.denominator}      ", self.cols)
        if self.mtc:
            tag = "MTC"
        else:
            tag = "t  "

        self.wh.addnstr(2, 1, f"{tag}: {self.h:2}.{self.m:02}.{self.s:02}.{self.f:02} @ {self.rate}/s    ", self.cols)
        if self.loop:
            loopMode = "yes"
        else:
            loopMode = "no"
        self.wh.addnstr(8, 1, f"Loop: {loopMode:10}", self.cols)
        self.wh.addnstr(9, 1, f"Transpose: {self.transpose}      ", self.cols)
        self.wh.refresh()

    def refresh(self):
        self.wh.refresh()

    def setLoop(self, value: bool):
        self.loop = value
        self.showValues()

    def setTimeCode(self, value: bool):
        self.mtc = value
        self.showValues()

    def setTranspose(self, value):
        self.transpose = value
        self.showValues()

    def updateValues(self, m: dict):
        self.bpm = round(6000000000 / m['tempo']) / 100
        self.bar = m['bar']
        self.beat = m['beat']
        self.numerator = m['signature'][0]
        self.denominator = m['signature'][1]
        self.lenSeconds = m['lengthSeconds']
        if 'mtc' in m:
            self.h = m['mtc']['hour']
            self.m = m['mtc']['min']
            self.s = m['mtc']['sec']
            self.f = m['mtc']['frame']
            self.rate = m['mtc']['rate']
        self.playing = m['playing']
        self.hasNewValues = True
        #self.showValues()

    def resize(self, rows: int, cols: int):
        self.cols = cols - 2
        self.wh.resize(rows, cols)
        self.wh.clear()
        self.wh.border()
        self.showValues()

class Settings:

    def __init__(self):
        self.home = str(Path.home())
        self.homedir = f"{self.home}/.cursedsmfplay/"
        if not os.path.isdir(self.homedir):
            os.mkdir(self.homedir, 0o700)
        self.settingsFileName = f"{self.homedir}settings.json"
        try:
            with open(self.settingsFileName, "r") as f:
                data = f.read()
                self.jsonData = json.loads(data)
        except:
            self.jsonData = {"home":self.home, "lastworkingdirectory":os.getcwd(), "mtc":False, "loop":False}
            self.createSettingsFile()

    def getLoopMode(self):
        if "loop" in self.jsonData:
            return self.jsonData["loop"]
        else:
            return False

    def getMtcMode(self):
        if "mtc" in self.jsonData:
            return self.jsonData["mtc"]
        else:
            return False

    def setLoopMode(self, mode:bool):
        self.jsonData["loop"] = mode
        self.createSettingsFile()

    def setMtcMode(self, mode:bool):
        self.jsonData["mtc"] = mode
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
        self.eventStop = None
        self.mfset = MidifileSet()
        self.mfset.scanDir()
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
        self.infoscreen = InfoScreen(curses.newwin(self.rows, self.infow, 0, self.wdir))
        self.winDirectory = curses.newwin(self.rows-3, self.wdir, 0, 0)

        self.transpose = 0
        self.resetScreen()


    def resetScreen(self):
        self.winDirectory.clear()
        self.rows, self.cols = self.screen.getmaxyx()
        self.wdir = self.cols - self.infow
        self.rows -= 2
        self.infoscreen.resize(self.rows-2, self.infow)
        self.winDirectory.resize(self.rows-2, self.wdir)
        self.winDirectory.clear()
        self.showDirectory()

    def update(self, msgDict: dict):
        self.infoscreen.updateValues(msgDict)

    def showDirectory(self):
        self.winDirectory.clear()
        self.winDirectory.border()
        ls = self.mfset.fetch()
        for i in range(self.rows - 4):
            if i + self.topindex < len(ls):
                if i + self.topindex == self.indexfile:
                    color = curses.color_pair(curses.COLOR_BLUE + 8)
                else:
                    color = curses.color_pair(curses.COLOR_BLACK)
                if ls[i+self.topindex][1] == 'dir':
                    dirStr = '>'
                else:
                    dirStr = ' '
                self.winDirectory.addnstr(i + 1, 1, f"{dirStr} {str(ls[i + self.topindex][0]):200}", self.wdir - 2, color)
        cwd = f"{os.getcwd()}/"
        self.winDirectory.refresh()
        self.screen.addnstr(self.rows-2, 1, f"{cwd:200}", self.cols - 2, curses.color_pair(curses.COLOR_BLACK))
        self.screen.refresh()

    def toogleLoop(self):
        self.loop = not self.loop
        self.settings.setLoopMode(self.loop)
        self.infoscreen.setLoop(self.loop)

    def toggleTimeCode(self):
        self.timeCode = not self.timeCode
        self.infoscreen.setTimeCode(self.timeCode)
        self.settings.setMtcMode(self.timeCode)
        self.smfPlayer.setSendMTC(self.timeCode)

    def interpretKey(self, key):
        #self.screen.addstr(self.rows + 1, 0, f'{key}          ')
        #self.screen.refresh()
        if 'KEY_UP' == key:
            files = self.mfset.fetch()
            self.indexfile -= 1
            if self.indexfile < 0:
                self.indexfile = 0
            if self.indexfile < self.topindex + 3:
                self.topindex -= int(self.rows / 2)
            if self.topindex < 0:
                self.topindex = 0
            self.showDirectory()
        elif 'KEY_DOWN' == key:
            files = self.mfset.fetch()
            self.indexfile += 1
            if self.indexfile >= len(files):
                self.indexfile = len(files) - 1
            if self.indexfile > self.topindex + (self.rows - 5):
                self.topindex += int(self.rows / 2)
            self.showDirectory()
        elif key in ['r', 'R']: #'KEY_RESIZE',
            curses.resizeterm(self.screen.getmaxyx())
            self.resetScreen()
        elif key in ['+']:
            self.transpose += 1
            self.infoscreen.setTranspose(self.transpose)
            self.smfPlayer.setTranspose(self.transpose)
        elif key in ['-']:
            self.transpose -= 1
            self.infoscreen.setTranspose(self.transpose)
            self.smfPlayer.setTranspose(self.transpose)
        elif key in [27, 'q', 'Q']:
            if self.eventStop is not None:
                self.eventStop.set()
            time.sleep(0.2)
            return False
        elif key in ['l', 'L']:

            self.toogleLoop()
        elif key in ['t', 'T']:
            self.toggleTimeCode()
        elif key in ['KEY_LEFT', '\b']:
            self.mfset.changedir("..")
            self.mfset.scanDir()
            self.indexfile = 0
            self.topindex = 0
            self.showDirectory()
        elif key in ['KEY_ENTER','KEY_RIGHT']:
            files = self.mfset.fetch()
            if files[self.indexfile][1] == 'dir':
                self.mfset.changedir(files[self.indexfile][0])
                flog.write(f"   -> {os.getcwd()}\n")

                self.mfset.scanDir()
                flog.write(f"   -> {self.mfset.fetch()}\n")
                self.indexfile = 0
                self.topindex = 0
                self.showDirectory()
            else:
                try:
                    if self.eventStop is not None:
                        self.eventStop.set()
                        time.sleep(0.1)
                except:
                    pass

                self.eventStop = Event()
                if self.loop:
                    loopcnt = 99999
                else:
                    loopcnt = 1
                midifile = f"{self.mfset.cwd}/{files[self.indexfile][0]}"
                self.playerThread = Thread(name='player',
                                           target=self.smfPlayer.play_file,
                                           args=(
                                           midifile, self.eventStop, self.update, loopcnt, self.transpose))
                self.playerThread.start()
                self.settings.setCurrentWorkingDirectory(self.mfset.cwd)

        elif key in [' ', 's', 'S']:
            try:
                self.eventStop.set()
            except:
                pass
        self.screen.move(1, self.wdir + self.rows - 2)
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
        self.loop = self.settings.getLoopMode()
        self.timeCode = self.settings.getMtcMode()
        self.infoscreen.loop = self.loop
        self.infoscreen.mtc = self.timeCode
        self.smfPlayer.setSendMTC(self.timeCode)

    def run(self) -> bool:

        midiout = rtmidi.MidiOut()
        midiout.open_virtual_port("midi-curse")
        self.smfPlayer = smfplayout(midiout)
        self.loadSettings()
        self.resetScreen()
        self.infoscreen.showValues()
        while True:
            try:
                time.sleep(0.02)
                key = self.screen.getkey()
                if key != -1:
                    if key == 'KEY_RESIZE':
                        self.cleanExit()
                        return True
                    elif not self.interpretKey(key):
                        self.cleanExit()
                        print("Terminating...")
                        return False

            except Exception as e:
                #print("Exception raised:", e)
                time.sleep(0.01)
                if self.infoscreen.hasNewValues:
                    self.infoscreen.showValues()


def main(cursesWindow):
    app = App()
    while(app.run()):
        time.sleep(0.05)
        app = App()


if __name__ == '__main__':
    wrapper(main)

