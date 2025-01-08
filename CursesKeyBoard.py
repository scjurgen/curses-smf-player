#!/usr/bin/env python3

import curses
from curses import wrapper
import json
import os
import rtmidi
from pathlib import Path
import time
from typing import Dict, Optional

class Settings:
    def __init__(self):
        self.home: str = str(Path.home())
        self.home_dir: str = f"{self.home}/.curseskeyplay/"
        if not os.path.isdir(self.home_dir):
            os.mkdir(self.home_dir, 0o700)
        self.settings_file_name: str = f"{self.home_dir}settings.json"
        try:
            with open(self.settings_file_name, "r") as f:
                data = f.read()
                self.json_data: Dict = json.loads(data)
        except:
            self.json_data: Dict = {"home": self.home, "lastworkingdirectory": os.getcwd(), "arpeggiator": False}
            self.create_settings_file()

    def set_current_working_directory(self, path: str) -> None:
        self.json_data["lastworkingdirectory"] = path
        self.create_settings_file()

    def create_settings_file(self) -> None:
        with open(self.settings_file_name, "w") as f:
            s = json.dumps(self.json_data)
            f.write(s)

class App:
    def __init__(self):
        self.settings: Optional[Settings] = None
        self.midi_out: Optional[rtmidi.MidiOut] = None
        self.screen: curses.window = curses.initscr()
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
        self.info_w: int = 30
        self.index_file: int = 0
        self.top_index: int = 0
        self.rows, self.cols = self.screen.getmaxyx()
        self.rows -= 2
        self.width_directory: int = self.cols - self.info_w

        self.transpose: int = 0
        self.baseNote: int = 12
        self.velocity: int = 100
        self.reset_screen()
        self.active_notes: Dict[int, int] = {}
        self.notes_off_counter: int = 0
        self.octave: int = 3
        self.modwheel_value: int = 0
        self.pitchbend_value: int = 8192
        self.keyboard_display: list = ['-'] * 88
        self.legend: str = """\nControls:
  - Arrow Up/Down: Change octave
  - Keys 1/2: Pitchbend down/up
  - Keys 3-8: Modwheel control (0-127)
  - C/V: Decrease/Increase velocity
  - Space: Panic (all notes off)
  - Esc: Exit
  - Keyboard keys (asdfghjkl;'wetyuop): Play notes
"""

    def reset_screen(self):
        self.rows, self.cols = self.screen.getmaxyx()
        self.width_directory = self.cols - self.info_w
        self.rows -= 2
        self.screen.clear()
        self.screen.refresh()

    def tick_auto_notes_off(self) -> None:
        if self.notes_off_counter > 0:
            self.notes_off_counter -= 1
            if self.notes_off_counter == 0:
                for key, value in list(self.active_notes.items()):
                    self.midi_out.send_message([0x80, self.baseNote + key, 64])
                    del self.active_notes[key]
                    self.keyboard_display[key] = '-'
                self.update_keyboard_display()

    def handle_note_on(self, h: int) -> None:
        h += self.octave * 12
        if h in self.active_notes:
            del self.active_notes[h]
            self.midi_out.send_message([0x80, self.baseNote + h, 64])
            self.keyboard_display[h] = '-'
        else:
            self.notes_off_counter = 100000
            self.midi_out.send_message([0x90, self.baseNote + h, self.velocity])
            self.active_notes[h] = self.velocity
            self.keyboard_display[h] = '#'
        self.update_keyboard_display()

    def send_note(self, k: str):
        key_note_map = {
            'a': 0, 'w': 1, 's': 2, 'e': 3, 'd': 4, 'f': 5, 't': 6, 'g': 7,
            'y': 8, 'h': 9, 'u': 10, 'j': 11, 'k': 12, 'o': 13, 'l': 14, 'p': 15,
            ';': 16, '\'': 17
        }
        if k in key_note_map:
            h = key_note_map[k]
            self.handle_note_on(h)

    def update_keyboard_display(self) -> None:
        keyboard_str = ''.join(self.keyboard_display[self.octave*12:(self.octave+2)*12])
        self.screen.addstr(2, 1, f"Keyboard: {keyboard_str}")
        self.screen.addstr(3, 1, f"Octave: {self.octave}-{self.octave+1}")
        self.screen.addstr(4, 1, f"Velocity: {self.velocity}")
        self.screen.addstr(5, 1, f"Modwheel: {self.modwheel_value}")
        self.screen.addstr(6, 1, f"Pitchbend: {self.pitchbend_value}")
        self.screen.addstr(8, 1, self.legend)
        self.screen.refresh()

    def send_modwheel(self, key: int) -> None:
        value = (key - 3) * 127 // 5
        self.modwheel_value = value
        self.midi_out.send_message([0xB0, 1, value])
        self.update_keyboard_display()

    def send_pitchbend(self, direction: int) -> None:
        step = 2048 if direction > 0 else -2048
        self.pitchbend_value += step
        self.pitchbend_value = max(0, min(16383, self.pitchbend_value))
        lsb = self.pitchbend_value & 0x7F
        msb = (self.pitchbend_value >> 7) & 0x7F
        self.midi_out.send_message([0xE0, lsb, msb])
        self.update_keyboard_display()

    def reset_pitchbend(self) -> None:
        self.pitchbend_value = 8192
        self.midi_out.send_message([0xE0, 0x00, 0x40])
        self.update_keyboard_display()

    def panic(self) -> None:
        for note in range(128):
            self.midi_out.send_message([0x80, note, 0])
        self.active_notes.clear()
        self.keyboard_display = [' '] * 88
        self.update_keyboard_display()

    def interpret_key(self, key: str) -> bool:
        self.screen.addstr(self.rows + 1, 0, f'{key}          ')
        self.screen.refresh()
        match key:
            case 'KEY_UP':
                self.octave = min(6, self.octave + 1)
            case 'KEY_DOWN':
                self.octave = max(0, self.octave - 1)
            case '1':
                self.send_pitchbend(-1)
            case '2':
                self.send_pitchbend(1)
            case '3' | '4' | '5' | '6' | '7' | '8':
                self.send_modwheel(int(key))
            case 'c' | 'C':
                self.velocity = max(1, self.velocity - 5)
            case 'v' | 'V':
                self.velocity = min(127, self.velocity + 5)
            case ' ':
                self.panic()
            case '\x1b':
                return False
            case _ if key in "asdfghjkl;'wetyuop":
                self.send_note(key)
        self.update_keyboard_display()
        return True

    def clean_exit(self) -> None:
        curses.nocbreak()
        self.screen.keypad(False)
        curses.echo()
        curses.endwin()

    def load_settings(self) -> None:
        self.settings = Settings()
        try:
            os.chdir(self.settings.json_data["lastworkingdirectory"])
        except:
            print("couldn't go to last directory")
            self.settings.set_current_working_directory(os.getcwd())

    def run(self) -> bool:
        self.midi_out = rtmidi.MidiOut()
        self.midi_out.open_virtual_port("midi-curse")
        self.update_keyboard_display()
        while True:
            self.tick_auto_notes_off()
            try:
                time.sleep(0.001)
                key = self.screen.getkey()
                if key != -1:
                    match key:
                        case 'KEY_RESIZE':
                            self.clean_exit()
                            return True
                        case _:
                            if not self.interpret_key(key):
                                self.clean_exit()
                                print("back to shell...")
                                return False
                else:
                    self.reset_pitchbend()
            except Exception:
                time.sleep(0.001)

def main(curses_window) -> None:
    app = App()
    while app.run():
        time.sleep(0.01)
        app = App()

if __name__ == '__main__':
    wrapper(main)

