# mode7kit flyer example

dizworld's Mode Y view: a perspective floor under a Mode 1 sky. The floor is
mode7kit's default `M7Plain` over its transport `M7HDMA`. The sky is this
example's own code (`src/bands.r65`, `src/horizon.r65`): `Horizon`, a sky
band in Mode 1 over the floor's horizon with a haze under it, on per-line
BG mode and layer bands (`M7Bands`). mode7kit has no bands of its own; see
[How the sky is built](#how-the-sky-is-built).

- **D-pad** left/right turns, up/down flies.
- **L/R** lower and raise the camera.
- **X/B** tilt the view up and down.
- **Start** mirrors the view.

Five world points are projected each frame with `M7Plain::to_screen`
into `OBJECT_SCREEN`, where the tests check them. The ROM draws no
sprites.

```bash
make             # fetch dependencies (mode7kit by path, stdlib from git) and build build/FLYER.smc
pytest tests     # drive the ROM in Mesen-GDB (pip install -e Mesen-GDB/python)
```

The tests set a view by writing mode7kit's state (the camera's heading,
height and pitch), or by pressing the ROM's buttons. They check
mode7kit's tables, the floor's rows in every quadrant, the floor's and the
bands' HDMA tables, the pitch,
the vertical flip and the floor projection against the same formulas in
Python.

## How the sky is built

`src/bands.r65` and `src/horizon.r65` are this example's code, not
mode7kit's. They build on its transport (the double buffer they follow and
the HDMAEN shadow they join) and read the floor only through `Mode7Scan`:
its rows' region `begin()..end()` and its `camera()`. The frame splits the
floor's `update()` around the sky's, so the sky's bands are ready with the
frame they go with:

```rust
M7Plain::build(0, 224);
Horizon::update();
M7Plain::publish();
```

and the NMI handler runs `M7Plain::nmi()` then `Horizon::nmi()`.

### `src/bands.r65`: per-line BG mode and layers

`m7k_bands!` writes a bands type: the screen as up to `max` runs of lines,
each with its own BGMODE and TM, and optionally a 16-line haze ramp at the
top of one band. Its tables are double-buffered with a transport and shown
with its front buffer (`show(k)`, `front_index()`).

| Channel | Register | Table | Mode |
|---|---|---|---|
| `ch_mode` | BGMODE $2105 | `bgm`, `max·4 + 1` bytes a buffer | direct, once: (lines, mode) per band |
| `ch_tm` | TM $212C | `tmt`, the same | direct, once: (lines, tm) per band |
| `ch_col` | COLDATA $2132 | `col`, `max·6 + 4` bytes a buffer | indirect: black over each band, the ramp a byte a line, black |

COLDATA is indirect, reading a 17-byte copy of black and the ramp
(`M7K_FADE[0]`, `[17..33]`) that `setup` puts in the bands' state: a fill
writes three entries instead of the 16 ramp bytes. `M7K_FADE: [u8; 33]` is
dizworld's `build_fade_table`.

| Function | Does |
|---|---|
| `set_count(n)`, `set_band(i, lines, mode, tm)`, `set_lines(i, lines)` | The layout: `mode` is sneslib's `BG`, `tm` the TM byte. The last band takes the rest of the screen, whatever its `lines`. A change bumps the version. |
| `set_haze(i)` | The ramp at the top of band i (`M7K_NO_HAZE`: none); needs a COLDATA channel. Before `setup`. |
| `setup()` | The channels on buffer 0, both buffers filled; with a haze, the ramp's copy, CGWSEL = 0 and CGADSUB = add on BG1; the channels in the transport's shadow |
| `stop()` | The channels out of the shadow. BGMODE, TM and COLDATA keep the last values their tables wrote. |
| `fill_back()`, `fill(k)` | The back buffer's tables, skipped when its key matches the version; buffer k's, always |
| `show(k)` | Points the channels at buffer k |
| `back_index()`, `front_index()` | The transport's buffer being built, and the one on screen after its `commit()` |

The tables are written in place with direct stores (`m7k_band_hold!`,
`m7k_band_ind!`), not the far-pointer table writers.

### `src/horizon.r65`: `Horizon`

`m7k_horizon!` writes the background of dizworld's view: a sky band in
another BG mode above a floor, a haze under the horizon, and an optional
HUD band under the floor. It is **not a `Mode7`**. It names its floor (any
`Mode7Scan`) and reads the floor's last build, `begin()`, `end()` and
`camera()`; its bands are the sky (the lines above `begin()`), the floor
(Mode 7, `begin()..end()`) and the HUD. The game keeps the floor as its
view: it sets the floor up, builds and publishes it, commits it in the
NMI handler and projects through it.

The bands must be filled for the frame the floor publishes, so the game
splits the floor's `update()` around the background's:

```rust
M7Plain::build(0, 224 - hud);   // hud is 0 without a HUD band
Horizon::update();
M7Plain::publish();
```

| Function | Does |
|---|---|
| `set_sky(sky_mode: BG, sky_tm, ground_tm)`, `set_haze(on)` | Before `setup`. Defaults: `BG::Mode1`, BG2 sky, BG1 floor, no haze. |
| `set_hud(lines, mode: BG, tm)` | A band of `lines` at the bottom (0: none); the floor builds `224 − lines`. Before `setup`. |
| `setup()` | The bands: split at line 64, the floor, the HUD. After the floor's `setup`. |
| `stop()` | The bands'. The floor stops on its own. |
| `update()` | The sky and floor bands' lines at the floor's `begin()`/`end()`, `fill_back()`, and the back buffer's sky scroll. After the floor's `build`, before its `publish`. |
| `nmi()` | The bands' `show` of the front buffer. After the floor's `nmi()`. |
| `sky_scroll() -> u16, u16` | dizworld's BG2 parallax for the frame on screen: hofs = −(angle·4) & 0x3FF, vofs = 240 − horizon. Read in the NMI handler, after `nmi()`. |

The sky scroll is kept per transport buffer, like the bands' tables, so
`nmi()` needs no flip flag: whatever buffer is in front, its bands and its
scroll go together.

## Assets

`assets/` holds dizworld's Mode 7 map, sky and palette, unchanged:

- **dizworld** by Brad Smith,
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- **16x16 Forest Tiles** by Sharm,
  [OpenGameArt](https://opengameart.org/content/16x16-forest-tiles) (CC BY 4.0).
- **Ocean Background** by KnoblePersona,
  [OpenGameArt](https://opengameart.org/content/ocean-background) (CC BY 3.0).
