from mesen_gdb.rom_driver import rom_state


@rom_state
def title(s):
    s.wait(60)                      # Title loaded and faded in


@rom_state(parent=title)
def game(s):
    s.start().wait(60)              # mosaic in, then Active
