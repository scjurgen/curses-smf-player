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
        self.home_dir = f"{self.home}/.curseskeyplay/"
        if not os.path.isdir(self.home_dir):
            os.mkdir(self.home_dir, 0o700)
        self.settings_file_name = f"{self.home_dir}settings.json"
        try:
            with open(self.settings_file_name, "r") as f:
                data = f.read()
                self.json_data = json.loads(data)
        except:
            self.json_data = {"home": self.home, "lastworkingdirectory": os.getcwd(), "arpeggiator": False}
            self.create_settings_file()

    def set_current_working_directory(self, path: str):
        self.json_data["lastworkingdirectory"] = path
        self.create_settings_file()

    def create_settings_file(self):
        with open(self.settings_file_name, "w") as f:
            s = json.dumps(self.json_data)
            f.write(s)


class App:
    def __init__(self):
        self.settings = None
        self.midi_out = None
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
        self.info_w = 30
        self.index_file = 0
        self.top_index = 0
        self.rows, self.cols = self.screen.getmaxyx()
        self.rows -= 2
        self.width_directory = self.cols - self.info_w

        self.transpose = 0
        self.baseNote = 12
        self.velocity = 120
        self.reset_screen()
        self.active_notes = {}
        self.notes_off_counter = 0
        self.octave = 3
        
    def handle_note_on(self, h: int):
        h += self.octave * 12
        if h in self.active_notes:
            del self.active_notes[h]
            self.midi_out.send_message([0x80, self.baseNote + h, 64])
            self.screen.addstr(2, h, '-')
        else:
            self.notes_off_counter = 100000
            self.midi_out.send_message([0x90, self.baseNote + h, self.velocity])
            self.active_notes[h] = self.velocity
            self.screen.addstr(2, h, 'O')

    def tick_auto_notes_off(self):
        if self.notes_off_counter > 0:
            self.notes_off_counter -= 1
            if self.notes_off_counter == 0:
                for key, value in self.active_notes.items():
                    self.midi_out.send_message([0x80, self.baseNote + key, 64])

    def send_note(self, k: str):
        key_note_map = {
            'a': 0, 'w': 1, 's': 2, 'e': 3, 'd': 4, 'f': 5, 't': 6, 'g': 7,
            'y': 8, 'h': 9, 'u': 10, 'j': 11, 'k': 12, 'o': 13, 'l': 14, 'p': 15,
            ';': 16, '\'': 17
        }
        if k in key_note_map:
            h = key_note_map[k]
            self.handle_note_on(h)

    def reset_screen(self):
        self.rows, self.cols = self.screen.getmaxyx()
        self.width_directory = self.cols - self.info_w
        self.rows -= 2
        self.screen.addstr(2, 1, "Hello")

    def interpret_key(self, key):
        # self.screen.addstr(self.rows + 1, 0, f'{key}          ')
        # self.screen.refresh()

        if 'KEY_UP' == key:
            self.octave += 1
        elif 'KEY_DOWN' == key:
            self.octave -= 1
        elif key in ['+']:
            pass
        elif key in ['-']:
            pass
        elif key in ['\x1b']:
            return False
        elif key in "asdfghjkl;'wetyuop":
            self.send_note(key)
        self.screen.move(1, self.width_directory + self.rows - 2)
        # self.screen.addstr(1, 2, f" {key} {ord(key)}     ")
        return True

    def clean_exit(self):
        curses.nocbreak()
        self.screen.keypad(False)
        curses.echo()
        curses.endwin()

    def load_settings(self):
        self.settings = Settings()
        try:
            os.chdir(self.settings.json_data["lastworkingdirectory"])
        except:
            print("couldn't go to last directory")
            self.settings.set_current_working_directory(os.getcwd())

    def run(self) -> bool:

        self.midi_out = rtmidi.MidiOut()
        self.midi_out.open_virtual_port("midi-curse")
        # index = 0
        while True:
            self.tick_auto_notes_off()
            # index += 1
            # self.screen.addstr(4, 2, f" {index}     ")
            try:
                time.sleep(0.001)
                key = self.screen.getkey()
                if key != -1:
                    if key == 'KEY_RESIZE':
                        self.clean_exit()
                        return True
                    elif not self.interpret_key(key):
                        self.clean_exit()
                        print("back to shell...")
                        return False

            except Exception as e:
                # print("Exception raised:", e)
                time.sleep(0.001)


def main(curses_window):
    app = App()
    while (app.run()):
        time.sleep(0.01)
        app = App()


if __name__ == '__main__':
    wrapper(main)
