# mode7kit top-down example

dizworld's Mode 7 map seen from above, with `static.r65`: `M7Static`, one
matrix a frame.

- **D-pad** up/down moves along the heading, left/right moves across it.
- **L/R** turn.
- **A/X** zoom in and out.
- **Y/B** stretch and squash the vertical axis only.

The ROM draws no sprites.

```bash
make             # fetch dependencies (mode7kit by path, stdlib from git) and build build/TOPDOWN.smc
pytest tests     # drive the ROM in Mesen-GDB (pip install -e Mesen-GDB/python)
```

The tests set a view by writing mode7kit's state (the camera's heading,
`M7Static`'s zoom), or by pressing the ROM's buttons. They check mode7kit's
tables, `M7Static`'s matrix and the camera against the same formulas in
Python, that the floor and horizon tables and state are absent from a build
that doesn't include them, and that Static mode never writes HDMAEN.

## Assets

`assets/` holds dizworld's Mode 7 map and its palette, unchanged:

- **dizworld** by Brad Smith,
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **16x16 Forest Tiles** by Sharm,
  [OpenGameArt](https://opengameart.org/content/16x16-forest-tiles) (CC BY 4.0).
