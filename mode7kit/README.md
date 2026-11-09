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
- **`M7Plain`** (`plain.r65`): a Mode Y perspective floor, one matrix a
  scanline by HDMA, that tilts up and down by sliding its picture.
- **`M7PlaneRotation`** (`plain_rotation.r65`): the perspective plane at a
  true pitch angle, from about 8° down to straight down. Its
  foreshortening changes with the tilt as a real camera's does. It costs
  more than the floor to turn, except straight down, where every line
  shares one matrix.

A sky above the floor, a HUD band under it and a split screen of two
floors are the game's to build on the floor: `examples/flyer/` and
`examples/split/` each carry their own, with the per-line BG mode and layer
bands they need.

| `Mode7` method | Does |
|---|---|
| `setup(repeat, flip)` | Mode 7, M7SEL and the view's own hardware, in force blank |
| `set_camera(&cam)`, `camera()` | The `M7Camera` the view follows from then on (`M7K_CAMERA` until called) |
| `update()` | Builds the next frame from the camera and the view's properties |
| `nmi()` | Commits it; call from the NMI handler |
| `to_screen(x, y) -> sx, sy, size` | The screen pixel of a world point, and the size of a texel there (8.8 pixels); `sy == M7K_HIDDEN` when it can't be drawn |
| `to_world(sx, sy) -> on, x, y` | The world point under a pixel, and whether it's on the map |
| `set_repeat`, `set_flip`, `repeat`, `flip` | M7SEL |

Call them on the type: `M7Static::update()`, `M7Plain::nmi()`. The HDMA
views (`M7Plain`, `M7PlaneRotation`, a transport) also have `stop()`,
which turns their channels off when a game switches away from them. The
camera carries the height and the pitch, which each view reads its own
way; `M7Static` has its own zoom, `M7Static::set_zoom(zx, zy)`.

## Files

Include the file of the view you use; the files it needs come with it.
Tables build at compile time.

| File | Gives you | ROM tables | RAM |
|---|---|---|---|
| `static.r65` | `M7Static` | sin/cos, reciprocal (1.2 KB) | 38 B |
| `plain.r65` | `M7Plain`, the perspective floor (a `Mode7Scan`) | + depth scale (2.3 KB) and per-height tables (640 B) | + 0.9 KB |
| `plain_rotation.r65` | `M7PlaneRotation`, the plane at a true pitch (a `Mode7Scan`) | + depth scale (2.3 KB) | + 0.9 KB |
| `hdma.r65` | the transport macro `m7k_hdma!` and `M7HDMA`, the per-line views' transport, for your own effects, HDMA channels 2–3 | none | + 3.7 KB (16 B a line) |
| `core.r65` | the `Mode7` and `Mode7Scan` traits, `M7Coord`, `M7Camera` and the world-coordinate helpers, the sin/cos and zoom reciprocal tables, the M7SEL enums, VRAM upload macros | sin/cos (640 B), reciprocal (512 B) | 7 B a camera |

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

A flyer over a perspective floor:

```rust
include!("mode7kit/plain.r65")

#[interrupt(nmi)]
fn vblank() { M7Plain::nmi(); }

// in force blank:
M7Plain::setup(M7Repeat::Wrap, M7Flip::None);
TM = 0x11;                        // BG1 + OBJ

loop {
    wait_nmi!();
    M7K_CAMERA.turn(2);
    M7K_CAMERA.set_height(height);
    M7K_CAMERA.set_pitch(pitch);         // the floor: a horizon shift in scanlines
    M7Plain::update();
    let sx, sy, size = M7Plain::to_screen(enemy_x, enemy_y);
}
```

For a sky above the horizon, split the floor's `update()` into
`M7Plain::build(0, 224)` and `M7Plain::publish()`, and set your sky's
lines from `M7Plain::begin()` between them, so they are ready with the
frame they go with. The flyer example does this.

A true pitch is `M7PlaneRotation` in place of `M7Plain`, with the same
calls; the camera's pitch is then an angle, 6..64 (64 straight down):

```rust
include!("mode7kit/plain_rotation.r65")
// ...
M7K_CAMERA.tilt(1);                      // look a step further down
M7PlaneRotation::update();
```

`examples/topdown/`, `examples/flyer/`, `examples/plane/` and
`examples/split/` are ROMs for each, with tests that drive them. `examples/beachball/` uses Static mode for
a single object: a spinning, squashing ball over a sprite floor.

## Units

| Quantity | Type | Meaning |
|---|---|---|
| angle | `u8` | 256 steps per turn |
| matrix entry | `i16` | 8.8 fixed point: `0x0100` is 1.0 |
| zoom | `u8` per screen axis | 64 is 1.0×, 128 magnifies 2×, 16 shrinks to ¼× |
| height | `u8` | the camera's height, 0..127 |
| pitch | `i8` | the camera's, −32..64. `M7Plain`: scanlines, negative looks down. `M7PlaneRotation`: an angle, 6 (8.4°) to 64 (straight down) |
| world coordinate | `M7Coord` | 10.6 fixed-point texels on the 1024×1024 plane |
| screen position | `i16` | pixels; off-screen points fall outside 0..255 / 0..223 |

## The camera and world coordinates

An `M7Coord` is a texel position in 10.6 fixed point. The plane is 1024
texels, exactly 65536 sixty-fourths, so ordinary u16 arithmetic wraps
around it, and `m7k_delta(a, b)` is the shortest way between two points.
`c.texel()` and `c.tile()` give the texel and the tile, and
`m7k_tile_index(x, y)` indexes a 128×128 map you keep for collision.

`M7K_CAMERA` is the camera every view follows until its `set_camera`:
`M7K_CAMERA.set(x, y)`, `.set_angle(a)`, `.turn(d)`, `.forward(speed)`
and `.strafe(speed)` (in 1/64 texels; negative goes back or left), and
`.set_height(h)`, `.set_pitch(p)` and `.tilt(d)`.
Switching views keeps the view where it was. For a second view, declare
another `#[lowram]` `M7Camera` and pass it: `FloorB::set_camera(&CAM_B)`.
The view keeps the pointer, so moving the camera moves the view.

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

`M7Plain::update()` builds next frame's floor around the camera. The
horizon is at scanline 32..95, unpitched; higher cameras see more ground.
The pitch tilts the view: the horizon moves by that many lines, and
everything on the floor with it. It is a y-shear, the look-up/look-down of
Doom-era engines: convincing for small tilts. The tables are
double-buffered and swap in vblank, so HDMA never shows a half-built floor;
if `update` runs late, the old floor stays. A frame whose heading and
height haven't changed rebuilds nothing.

`to_screen` on the floor returns `sy == M7K_HIDDEN` for points behind the
camera, past the horizon or below the floor; `M7Plain::depth()` is the
last point's distance, for sorting. Call the projections after `update` in
the same frame, so the sprites move with the floor they belong to.

On the floor, `M7Flip::Horizontal` mirrors the view; a vertical flip isn't
shown, since each scanline's matrix belongs to that scanline. It stays set,
for a return to Static mode.

## Your own per-line effect

`M7HDMA` (`include!("mode7kit/hdma.r65")`) is the per-line views'
transport: per-line matrices, double-buffered, with no math. Write rows into the back buffer with
`M7HDMA::set_line(row, a, b, c, d)`, set the view with `set_center`, and
finish with `M7HDMA::publish(top, rows)`: lines above `top` hold
`set_top`'s matrix, line `top + r` reads row r, and after `rows` lines the
matrix stops. In the NMI handler, `M7HDMA::commit()` shows it.

## Your own instances

The HDMA layers are macros, and each file declares one default instance.
For other sizes, other channels or more than one, declare your own:

```rust
include!("mode7kit/plain.r65")

m7k_hdma!(Hdma160, HDMA160, 160, 1, 3);          // 160 lines, channels 1 and 3
m7k_plain!(Floor, FLOOR, Hdma160, HDMA160, m7k_rows_mul);
```

| Macro | Makes |
|---|---|
| `m7k_hdma!(Name, STATE, lines, ch_ab, ch_cd)` | a transport of `lines` rows (16 bytes of RAM a line) |
| `m7k_plain!(Name, STATE, Hdma, HDMA_STATE, m7k_rows_mul)` | a floor in that transport, following `M7K_CAMERA` until its `set_camera` |

Instances you don't use cost nothing.

## Split screen

Two floors over one transport, each with its own camera
(`FloorB::set_camera(&CAM_B)`), each built into its half with
`build(top, lines)` and laid out as one frame with the transport's
segments. `examples/split/` builds one, with a sky band in each half; see
its README.

## Switching modes

A game with several views switches in vblank, straight after
`wait_nmi!()`:

```rust
M7Plain::stop();                 // only an HDMA view has one
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
| 2, 3 | `M7HDMA`: M7A/M7B, M7C/M7D |
| 1, 4–7 | free for the game (the flyer's sky bands use 4–6, the split's views 1 and 7) |

Your own instances can use any channels. In Static mode HDMAEN is yours.
With the floor, the transport writes it every vblank: add your own
channels with `M7HDMA::enable(mask)`.

The floor and the projections drive the hardware multiplier directly. An
NMI handler that interrupts them must not use it (`mul8`, `div16`, ...);
mode7kit's own `nmi()` functions don't.

## Cost

Measured by `tests/bench/`, in scanlines of a 262-line frame ("+ sky" is
the bench's own copy of the flyer's sky bands):

| Work | Scanlines |
|---|---|
| floor + sky, 160 ground lines, while turning | 144 |
| floor + sky, heading and height unchanged | 7 |
| floor + sky, looking fully down / fully up | 174 / 88 |
| a height change (the line tables) | + 159 |
| `to_screen` on the floor: visible / behind / far | 13 / 8 / 4 |
| `M7Static::update` | 10 |
| `M7PlaneRotation` turning at 22.5° / 45° / straight down | 182 / 275 / 10 |
| `M7PlaneRotation` pitch change (tables and rows) | 395 |

The flyer example, with five objects projected, runs at 60 fps while
turning; a frame that changes the height drops to 30.

## Credits

The perspective floor and the horizon follow dizworld by Brad Smith
([rainwarrior.ca](https://rainwarrior.ca)), CC BY 4.0, with its per-frame
divisions moved to compile time.
