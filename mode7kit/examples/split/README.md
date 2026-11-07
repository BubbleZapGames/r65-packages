# mode7kit split example

Two perspective floors on one screen, each following its own camera, as in
a two-player racer: `views.r65`'s `m7k_split!` over two floor instances.

- The default floor `M7Floor` follows `M7K_CAMERA` in the top half; a
  second instance, `FloorB` (`m7k_floor!`), follows `CAM_B` in the bottom.
- `Bands4` (`m7k_bands!`, four bands, no COLDATA) gives each half a Mode 1
  sky band over its Mode 7 floor.
- `M7Views` sets each band's Mode 7 center and BG1 scroll by HDMA. The sky
  is BG1 in Mode 1, so each half's sky scrolls with its own camera.

**Pad 1:** the D-pad turns (left/right) and flies (up/down) the top
camera; Y/A turn and X/B fly the bottom one. Both look down a little
(`set_pitch(-24)`), since a half shows the top of a full-screen floor.

```bash
make             # fetch dependencies (mode7kit by path, stdlib from git) and build build/SPLIT.smc
pytest tests     # drive the ROM in Mesen-GDB (pip install -e Mesen-GDB/python)
```

The tests write the cameras and check, a half at a time by screenshot,
that each half follows its own camera and leaves the other alone, and that
both cameras in one place give the same sky and, but for Mode 7's
sub-texel rounding, the same floor. They check the channels in HDMAEN and
the floors' horizons, the bands' and the views' tables.

The graphics are the flyer example's dizworld assets, read from
`../flyer/assets/`; see that example's README for the credits.
