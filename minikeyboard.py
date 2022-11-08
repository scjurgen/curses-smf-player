#!/usr/bin/env python3

from tkinter import Tk, Frame #importing only necessary stuff.

def keyrelease(e):
    print('The key was released: ', repr(e.char))

root = Tk()
f = Frame(root, width=100, height=100)
f.bind("<KeyRelease>", keyrelease)
f.pack()
root.mainloop()
