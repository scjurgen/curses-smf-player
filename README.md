
# Curses SMF Player

Small Midifile player using a curses interface.

The player can:
- send SMF format 0 and 1
- browses midifiles
- loops midifiles
- sends midi time code messages at 24 frames/sec (MTC)
- exposes a midi out interface as long as it is running (named ***midi-curse***)
- transposes
- show information: key, beats and bar, time signature

### Known Bugs
- show correct directory on start

## Todo

### Player

- tempo adjust
- set preroll

### Curse interface

- dir box
  - add playtime, extract tempo, signature, key
  - show path with wrapping or ellipsis
  - show current selected midi file settings
  - home directory key (h)
- add help box

