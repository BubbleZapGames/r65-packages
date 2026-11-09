# mode7kit plain rotation example

The flyer's view with a true pitch: mode7kit's `M7PlainRotation` over its
transport `M7HDMA`, under a Mode 1 sky. The sky is the flyer's own code,
copied into `src/` (`bands.r65`, `horizon.r65`): `Horizon` over the plain
instead of the floor. It reads the view only through `Mode7Scan`, so
the swap is one name in `src/horizon.r65`.

- **D-pad** left/right turns, up/down flies.
- **L/R** lower and raise the camera.
- **X/B** tilt the view up and down, from about 8° down to straight down.
- **Start** mirrors the view.

The camera starts at pitch 16 (22.5°). Unlike `M7Plain`, which slides its
picture to tilt, the ground's foreshortening changes as you tilt. Straight
down it is a flat map: one matrix for every line, so turning costs about
what `M7Static` does.

Five world points are projected each frame with
`M7PlainRotation::to_screen` into `OBJECT_SCREEN`, where the tests read
them. The ROM draws no sprites.

```bash
make             # fetch dependencies (mode7kit by path, stdlib from git) and build build/PLAINROT.smc
pytest tests     # drive the ROM in Mesen-GDB (pip install -e Mesen-GDB/python)
```

The tests write the camera's heading, scales, height and pitch and check:
- the line tables (the first ground line, the point under the camera,
  `line_z` and `line_dist`) against the same integer math in Python, at
  altitudes from the height and scale_y's whole range and past its
  clamps;
- the rows' four products in every quadrant, equal and stretched, and the
  pitch clamp at 6..64;
- the single held row straight down, and at height 128 that it is
  `M7Static`'s matrix for equal and stretched scales;
- `to_screen` against the view's own tables exactly;
- the picture and `to_screen` against an ideal ray-cast camera. At least
  85–99% of ground pixels must be within one texel, depending on the
  pitch; the error is the 8-bit depth scale.

The graphics are the flyer example's dizworld assets, read from
`../flyer/assets/`; see that example's README for the credits.
