# mode7kit

Mode 7 for SNES games written in [R65](https://github.com/BubbleZapGames/R65):
rotation, scaling, world coordinates with sprite projection, a perspective
floor, a sky band and a HUD band around it, and split-screen floors. A
rotating map costs a few hundred bytes; each layer above it is a file you
include, and anything you never call is left out of the ROM.

## Views

The Mode 7 matrix gets its values once a frame or once a scanline, and
mode7kit has a type for each way of using it. Each implements the `Mode7`
trait, so a game's loop and sprite code read the same in any:

- **`M7Static`** (`static.r65`): one matrix a frame, written in vblank. A
  top-down map that rotates, zooms, squashes and stretches. It touches no
  HDMA register, so HDMAEN stays yours.
- **`M7Floor`** (`floor.r65`): a Mode Y perspective floor, one matrix a
  scanline by HDMA, that tilts up and down.
- **`Horizon`** (`horizon.r65`): the floor with a sky band in another BG
  mode above it, a haze under the horizon, and a HUD band under it if you
  want one.
- **A split screen** (`views.r65`, `m7k_split!`): two floors, each
  following its own camera, stacked.

| `Mode7` method | Does |
|---|---|
| `setup(repeat, flip)` | Mode 7, M7SEL and the view's own hardware, in force blank |
| `update()` | Builds the next frame from the camera and the view's properties |
| `nmi()` | Commits it; call from the NMI handler |
| `to_screen(x, y) -> sx, sy, size` | The screen pixel of a world point, and the size of a texel there (8.8 pixels); `sy == M7K_HIDDEN` when it can't be drawn |
| `to_world(sx, sy) -> on, x, y` | The world point under a pixel, and whether it's on the map |
| `set_repeat`, `set_flip`, `repeat`, `flip` | M7SEL |
| `stop()` | Leaves the view, for a game that switches |

Call them on the type: `M7Static::update()`, `Horizon::nmi()`. Only the
properties differ: `M7Static::set_zoom(zx, zy)`, or
`M7Floor::set_height(h)` and `M7Floor::set_pitch(p)`.

## Files

Include the file of the view you use; the files it needs come with it.
Tables build at compile time.

| File | Gives you | ROM tables | RAM |
|---|---|---|---|
| `static.r65` | `M7Static` | sin/cos, reciprocal (1.2 KB) | 34 B |
| `hdma.r65` | `M7HDMA`: the per-line matrices, for your own effects, HDMA channels 2–3 | none | 3.7 KB (16 B a line) |
| `floor.r65` | `M7Floor`, the perspective floor | + depth tables (2.9 KB) | + 0.9 KB |
| `horizon.r65` | `Horizon`: a sky, a haze, a HUD; `M7Bands`, channels 4–6 | + fade (33 B) | + 140 B |
| `views.r65` | `M7Views`, channels 1 and 7, and `m7k_split!` | | + 200 B, + 0.9 KB a floor |
| `world.r65` | `M7Camera`, world-coordinate helpers | sin/cos | 5 B a camera |
| `rotate.r65`, `scale.r65` | the sin/cos and reciprocal tables | 640 B, 512 B | none |
| `core.r65` | the `Mode7` trait, `M7Coord`, the M7SEL enums, VRAM upload macros | none | none |

## Quick start

```toml
# r65.toml
[dependencies]
mode7kit = { git = "https://github.com/BubbleZapGames/r65-packages", version = "0.1" }
```

A rotating, zooming top-down map:

```rust
include!("mode7kit/static.r65")

#[interrupt(nmi)]
fn vblank() { M7Static::nmi(); }

#[entry]
fn main() -> ! {
    snes_init();
    mode7_upload_interleaved!(MAP_MD7);       // 32 KB .md7, in force blank
    M7Static::setup(M7Repeat::Wrap, M7Flip::None);
    TM = 0x11;
    loop {
        wait_nmi!();
        M7K_CAMERA.turn(1);
        M7K_CAMERA.forward(64);               // one texel along the heading
        M7Static::set_zoom(zoom, zoom);
        M7Static::update();
        let sx, sy, size = M7Static::to_screen(enemy_x, enemy_y);   // a sprite on the map
    }
}
```

A flyer over a perspective floor, with a Mode 1 sky:

```rust
include!("mode7kit/horizon.r65")

#[interrupt(nmi)]
fn vblank() {
    Horizon::nmi();
    let hofs, vofs = Horizon::sky_scroll();   // BG2's scroll
}

// in force blank:
Horizon::set_sky(0x01, 0x12, 0x11);   // sky: Mode 1, BG2 + OBJ; floor: BG1 + OBJ
Horizon::setup(M7Repeat::Wrap, M7Flip::None);

loop {
    wait_nmi!();
    M7K_CAMERA.turn(2);
    M7Floor::set_height(height);
    M7Floor::set_pitch(pitch);
    Horizon::update();
    let sx, sy, size = Horizon::to_screen(enemy_x, enemy_y);
}
```

`examples/topdown/`, `examples/flyer/` and `examples/split/` are ROMs for
each, with tests that drive them.

## Units

| Quantity | Type | Meaning |
|---|---|---|
| angle | `u8` | 256 steps per turn |
| matrix entry | `i16` | 8.8 fixed point: `0x0100` is 1.0 |
| zoom | `u8` per screen axis | 64 is 1.0×, 128 magnifies 2×, 16 shrinks to ¼× |
| height | `u8` | camera height for the floor, 0..127 |
| pitch | `i8` | scanlines, −32 (look down) to 64 (look up) |
| world coordinate | `M7Coord` | 10.6 fixed-point texels on the 1024×1024 plane |
| screen position | `i16` | pixels; off-screen points fall outside 0..255 / 0..223 |

## The camera and world coordinates

An `M7Coord` is a texel position in 10.6 fixed point. The plane is 1024
texels, exactly 65536 sixty-fourths, so ordinary u16 arithmetic wraps
around it, and `m7k_delta(a, b)` is the shortest way between two points.
`c.texel()` and `c.tile()` give the texel and the tile, and
`m7k_tile_index(x, y)` indexes a 128×128 map you keep for collision.

`M7K_CAMERA` is the camera `M7Static` and the floor follow:
`M7K_CAMERA.set(x, y)`, `.set_angle(a)`, `.turn(d)`, `.forward(speed)`
and `.strafe(speed)` (in 1/64 texels; negative goes back or left).
Switching views keeps the view where it was. Declare another `M7Camera`
for a second view.

The projections measure from the whole-texel camera the registers show,
so sprites stay on the ground, and they follow the reflection. `to_world`
says whether the point is on the map: always under `Wrap`.

## Static mode

`M7Static::update()` turns the view to the camera's heading, scales it by
`set_zoom(zx, zy)`, and pins the camera to `set_pivot(sx, sy)` (the screen
center by default). Equal zooms zoom; unequal ones squash and stretch, and
`set_zoom(64, 56)` corrects the SNES's 8:7 pixels.

For a matrix of your own, skip `update()`: `rotate`, `scale`,
`rotate_scale`, `identity`, or `set_matrix` with its inverse in
`set_inverse` if you want to project, and `set_center` for the view.

## The floor, the sky and the HUD

`M7Floor::update()` builds next frame's floor around the camera. The
horizon is at scanline 32..95, unpitched; higher cameras see more ground.
The pitch tilts the view: the horizon moves by that many lines, and
everything on the floor with it. It is a y-shear, the look-up/look-down of
Doom-era engines: convincing for small tilts. The tables are
double-buffered and swap in vblank, so HDMA never shows a half-built floor;
if `update` runs late, the old floor stays. A frame whose heading and
height haven't changed rebuilds nothing.

`to_screen` on the floor returns `sy == M7K_HIDDEN` for points behind the
camera, past the horizon or below the floor; `M7Floor::depth()` is the
last point's distance, for sorting. Call the projections after `update` in
the same frame, so the sprites move with the floor they belong to.

On the floor, `M7Flip::Horizontal` mirrors the view; a vertical flip isn't
shown, since each scanline's matrix belongs to that scanline. It stays set,
for a return to Static mode.

`Horizon` adds the bands around the floor, all before `setup`:
- `set_sky(sky_mode, sky_tm, ground_tm)` puts another BG mode above the
  horizon (Mode 1, typically, for a scrolling sky on BG2);
- `set_haze(true)` adds a fading fixed colour on BG1 under it;
- `set_hud(lines, mode, tm)` adds a band of its own at the bottom, and the
  floor stops above it.

`Horizon::sky_scroll()` gives a sky scroll that turns with the view and
meets the horizon. The floor's properties stay on `M7Floor`.

## Your own per-line effect

`M7HDMA` is the floor's transport: per-line matrices, double-buffered,
with no math. Write rows into the back buffer with
`M7HDMA::set_line(row, a, b, c, d)`, set the view with `set_center`, and
finish with `M7HDMA::publish(top, rows)`: lines above `top` hold
`set_top`'s matrix, line `top + r` reads row r, and after `rows` lines the
matrix stops. In the NMI handler, `M7HDMA::commit()` shows it.

## Your own instances

The HDMA layers are macros, and each file declares one default instance.
For other sizes, other channels or more than one, declare your own:

```rust
include!("mode7kit/horizon.r65")

m7k_hdma!(Hdma160, HDMA160, 160, 1, 3);          // 160 lines, channels 1 and 3
m7k_floor!(Floor, FLOOR, Hdma160, HDMA160, M7K_CAMERA, m7k_rows_mul);
m7k_bands!(Bands, BANDS, Hdma160, 3, 4, 5);      // 3 bands, no COLDATA channel
m7k_horizon!(Hud, HUD, Floor, Bands);            // then Hud::setup(...), Hud::update()...
```

| Macro | Makes |
|---|---|
| `m7k_hdma!(Name, STATE, lines, ch_ab, ch_cd)` | a transport of `lines` rows (16 bytes of RAM a line) |
| `m7k_floor!(Name, STATE, Hdma, HDMA_STATE, CAMERA, m7k_rows_mul)` | a floor following `CAMERA`, in that transport |
| `m7k_bands!(Name, STATE, Hdma, max, ch_mode, ch_tm[, ch_col])` | up to `max` bands; COLDATA (for the haze) only with `ch_col` |
| `m7k_horizon!(Name, STATE, Floor, Bands)` | a floor with a sky and a HUD |
| `m7k_views!(Name, STATE, Hdma, max, ch_center, ch_scroll)` | a Mode 7 view per band |
| `m7k_split!(Name, STATE, Hdma, Bands, Views, FloorA, FloorB)` | two floors stacked |

Instances you don't use cost nothing.

## Split screen

Two cameras, two floors over one transport, and the split preset:

```rust
include!("mode7kit/views.r65")

#[lowram]
static mut CAM_B: M7Camera = M7Camera { x: M7Coord(0x8000), y: M7Coord(0x8000), angle: 128 };

m7k_floor!(FloorB, FLOOR_B, M7HDMA, M7K_HDMA, CAM_B, m7k_rows_mul);
m7k_bands!(Bands4, BANDS4, M7HDMA, 4, 4, 5);
m7k_split!(Split, SPLIT, M7HDMA, Bands4, M7Views, M7Floor, FloorB);
```

Each half has a sky band and a floor band, and each half's view (the Mode
7 center and the BG1 scroll) is set by HDMA. The sky is BG1 in the sky's
BG mode, so each half's sky scrolls with its own camera: point BG1SC and
BG12NBA at the sky. A half shows the top of a full-screen floor, cropped,
so look down a little (`set_pitch(-24)`) to see more of it.

## Switching modes

A game with several views switches in vblank, straight after
`wait_nmi!()`:

```rust
Horizon::stop();
M7Static::setup(M7Static::repeat(), M7Static::flip());
// and the NMI handler now calls M7Static::nmi()
```

Nothing records which view you're in: your NMI handler calls the `nmi()`
of the one you're using. Each view keeps its own state, so calling the
other's functions does no harm, but answers for that other view.

## HDMA, DMA and the multiplier

| Channel | Used by default by |
|---|---|
| 0 | free for the game (the upload macros use it, in force blank) |
| 1, 7 | `M7Views`: M7X/M7Y, BG1 scroll (split screen only) |
| 2, 3 | `M7HDMA`: M7A/M7B, M7C/M7D |
| 4, 5, 6 | `M7Bands`: BGMODE, TM, COLDATA (6 with the haze only) |

Your own instances can use any channels. In Static mode HDMAEN is yours.
With the floor, the transport writes it every vblank: add your own
channels with `M7HDMA::enable(mask)`.

The floor and the projections drive the hardware multiplier directly. An
NMI handler that interrupts them must not use it (`mul8`, `div16`, ...);
mode7kit's own `nmi()` functions don't.

## Cost

Measured by `tests/bench/`, in scanlines of a 262-line frame:

| Work | Scanlines |
|---|---|
| floor + sky, 160 ground lines, while turning | 144 |
| floor + sky, heading and height unchanged | 7 |
| floor + sky, looking fully down / fully up | 174 / 88 |
| a height change (the line tables) | + 159 |
| `to_screen` on the floor: visible / behind / far | 13 / 8 / 4 |
| `M7Static::update` | 10 |

The flyer example, with five objects projected, runs at 60 fps while
turning; a frame that changes the height drops to 30.

## Credits

The perspective floor and the horizon follow dizworld by Brad Smith
([rainwarrior.ca](https://rainwarrior.ca)), CC BY 4.0, with its per-frame
divisions moved to compile time.
