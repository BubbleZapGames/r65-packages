# mode7kit flyer example

dizworld's Mode Y view: a perspective floor under a Mode 1 sky, with
`horizon.r65`'s default instances: `Horizon`, the floor `M7Floor` with a
sky band (`M7Bands`), over the transport `M7HDMA`.

- **D-pad** left/right turns, up/down flies.
- **L/R** lower and raise the camera.
- **X/B** tilt the view up and down.
- **Start** mirrors the view.

Five world points are projected each frame with `Horizon::to_screen`
into `OBJECT_SCREEN`, where the tests check them. The ROM draws no
sprites.

```bash
make             # fetch dependencies (mode7kit by path, stdlib from git) and build build/FLYER.smc
pytest tests     # drive the ROM in Mesen-GDB (pip install -e Mesen-GDB/python)
```

The tests set a view by writing mode7kit's state (the camera's heading,
`M7Floor`'s height and pitch), or by pressing the ROM's buttons. They check
mode7kit's tables, the floor's rows in every quadrant, the floor's and the
bands' HDMA tables, the pitch,
the vertical flip and the floor projection against the same formulas in
Python.

## Assets

`assets/` holds dizworld's Mode 7 map, sky and palette, unchanged:

- **dizworld** by Brad Smith,
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **16x16 Forest Tiles** by Sharm,
  [OpenGameArt](https://opengameart.org/content/16x16-forest-tiles) (CC BY 4.0).
- **Ocean Background** by KnoblePersona,
  [OpenGameArt](https://opengameart.org/content/ocean-background) (CC BY 3.0).
