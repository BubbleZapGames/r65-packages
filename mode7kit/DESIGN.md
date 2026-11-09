# mode7kit design

This is the maintainer reference for mode7kit, a modular Mode 7 library for SNES games written in
R65. The README is the user guide.

## Goals

- **One shape, several views.** M7A–D get their values once a frame
  (`M7Static`) or once a scanline by HDMA (a floor, a custom effect). They are built very differently, but a game uses them the same
  way: place a camera, build the frame, project sprites, commit in vblank.
  So `Mode7` is a trait, and each view is a type implementing it. A game's
  loop and sprite code read the same in any; only the properties differ.
- **Minimal to maximal.** A rotating map costs two small tables and 40
  bytes. A perspective floor costs about 4.4 KB of RAM, and a second floor
  over the same transport about 0.7 KB more. A game includes the file of the
  view it uses and gets the files it needs with it (`include!` runs each
  file once). Tables build at compile time with `const fn`, and the
  compiler removes code, tables and state a game never uses.
- **Modular by instances.** The HDMA layers (transport, floor) are
  instance macros: a game with other sizes, other channels or two floors
  writes its own instances, all with static dispatch. Each file ships a
  default instance, so the usual setup writes no macro.
- **Mode 7 only.** Per-line BG mode and layer bands, a sky over the
  horizon, a HUD band and a split screen are general HDMA, not Mode 7, so
  the package leaves them to the game. Their only tie to a floor is its
  rows' region (`Mode7Scan::band()`). `examples/flyer/` and
  `examples/split/` carry their own.
- **Measured, not estimated.** `tests/bench/` latches the V-counter
  around each piece; the costs below are its numbers, and its budgets
  catch a regression.
- **The math from the working demos.** Rotation follows
  `r65docs/build/examples/graphics/mode7.r65`. The perspective floor and the
  horizon follow the working main loop of `dizworld.r65`. Parts of dizworld
  that are dead or wrong (see [Notes on dizworld](#notes-on-dizworld)) are
  fixed rather than copied.
- **Plain R65.** The library uses no `asm!()` and never writes the `A`, `B`,
  `X` or `Y` registers itself (see [Code style](#code-style)).

## Files and layers

```
core.r65 ◄─┬─ static.r65                         M7Static
 (traits,  │
  tables)  └─ hdma.r65 ◄─┬─ plain.r65            M7HDMA ◄ M7Plain
             (m7k_hdma!, └─ plain_rotation.r65   M7HDMA ◄ M7PlainRotation
              M7HDMA)
```

| Layer | File | Writes | Default instance | `Mode7`? | ROM | RAM |
|---|---|---|---|---|---|---|
| core | `core.r65` | the `Mode7` and `Mode7Scan` traits, `M7Coord`, `M7Repeat`, `M7Flip`, `m7k_sin/cos`, `m7k_heading`, `m7k_recip`, `M7Camera`, register writers, the DMA channel array, the multiplies, uploads | none: the game declares its cameras | | 130 B (sin), 512 B (reciprocal), 2321 B (`M7K_ZRECIP`, for a per-line view) | none (7 B a game camera) |
| flat view | `static.r65` | `M7Static` | `M7K_STATIC` | yes | code | 31 B |
| transport | `hdma.r65` | `m7k_hdma!`: per-line matrices, double buffer, indirect tables, M7SEL and the view, HDMAEN; the HDMA table writers | `M7HDMA` (224 lines, ch 2–3) | no | code | 16·lines + 151 B an instance (3735 B for `M7HDMA`) |
| floor | `plain.r65` | `m7k_plain!`: a camera's perspective floor in a transport, its projections | `M7Plain` | yes, and `Mode7Scan` | 640 B | 723 B |
| plain rotation | `plain_rotation.r65` | `m7k_plain_rotation!`: the plain at a true pitch angle, its projections | `M7PlainRotation` | yes, and `Mode7Scan` | none | 729 B |

A game includes the file of the view it uses:

```rust
include!("mode7kit/static.r65")       // M7Static, the camera, the tables it uses
include!("mode7kit/plain.r65")        // M7Plain over M7HDMA
include!("mode7kit/plain_rotation.r65") // M7PlainRotation over M7HDMA
include!("mode7kit/hdma.r65")         // M7HDMA alone, for a game's own effect
```

The transport has no math and is not a `Mode7`: a custom per-line effect
drives it directly. A `Mode7` is what a game builds with `update()` and
projects with: `M7Static` or a floor.

Each instance keeps its state in one static with a static initializer, so
the first NMI after power-on commits sane values with no `init()`. The
state is mostly zeros (the transport's rows, the line tables), and R65
fills a long zero run at start-up instead of copying it from ROM, so an
initializer costs ROM only for its other bytes (21 B for `M7HDMA`'s 3735). This is
the nscene `SCENE_CONTROLLER` pattern: a library owns its state, and state
that nothing reads is dropped.

`#[bank(n)]` is a directive for everything after it, not an attribute on
one item, so the one table too large to share the includer's bank,
`M7K_ZRECIP`, sits at the end of `core.r65` under `#[bank(auto)]`,
declared `far static` as auto-bank mode requires. The preprocessor restores
the includer's bank after a package include (docs/packaging-system.md,
"Bank state leaks across include boundaries"), so this never rebanks the
game's code. The package's own code, default instances included, goes in
whatever bank the game includes it from, and a game's own instances in the
bank of the invocation. Functions are far by default, and `far_to_near`
demotes the ones whose callers are all in the same bank; trait calls
included.

## Instance macros

R65 has no generics. Each HDMA layer is therefore a macro that writes a
type, its impls and its state static, the nscene pattern
(`scene_fade_in!(Name, length)`). The default instances are each in the
file of the layer that uses them:

```rust
m7k_hdma!(M7HDMA, M7K_HDMA, 224, 2, 3);                                  // hdma.r65
m7k_plain!(M7Plain, M7K_PLAIN, M7HDMA, M7K_HDMA, m7k_rows_mul);          // plain.r65
m7k_plain_rotation!(M7PlainRotation, M7K_PLAIN_ROTATION, M7HDMA, M7K_HDMA,
                    m7k_plain_rows_mul);                                 // plain_rotation.r65
```

| Macro | Parameters |
|---|---|
| `m7k_hdma!(Name, STATE, lines, ch_ab, ch_cd)` | `lines`: matrix rows a buffer holds, at most 224. The channels for M7A/B and M7C/D. |
| `m7k_plain!(Name, STATE, Hdma, HDMA_STATE, rows)` | The transport it writes into, by type and state static; `rows`, the row-builder macro (`m7k_rows_mul`). The camera is passed at run time, to `setup`. |

- **Names.** R65 can't concatenate identifiers, so a macro is passed every
  name it creates: the type and its state static. A game using only the
  defaults names neither.
- **State.** The transport's and the floor's state hold arrays the HDMA or
  the build reads (rows, line tables), so they are `#[ram]`, bank $7E,
  the bank DASBn names (`M7K_RAM_BANK`). Their scalars cost a long access,
  a few a frame.
- **Channels by number.** `core.r65` declares the eight DMA channels as
  one array, `#[hw(0x4300)] static mut M7K_DMA: [M7KChannel; 8]`, a
  16-byte struct per channel. `M7K_DMA[$ch].a1t = addr` has a constant
  index and folds to one store to `$43n2`, so a channel number costs
  nothing and needs none of stdlib's channel-literal macros.
- **Sizes from parameters.** A type's arrays take their sizes from the
  macro's arguments (`ab: [i16; $lines * 4]`); a dependant reads them as
  associated consts (`Hdma::LINES`).
- **Several instances.** Two floors following two cameras and writing
  rows into one transport are what split-screen is. Two transports would
  need four matrix channels, and nothing needs that.
- **Doc comments.** Items a macro writes may carry `///`; the compiler
  drops them from the expansion. A `///` before an invocation documents
  the instance for a reader.

## core.r65: the `Mode7` trait

`core.r65` has the trait the views implement, the M7SEL enums, `M7Coord`,
the camera (below), two stateless register writers, the DMA channel array
(see [Instance macros](#instance-macros)), the fixed-point multiplies and
the upload macros. It declares no state: the game declares its cameras.
Its tables are the sin table, which the camera's movement and every
view's matrix read, and the zoom reciprocal (both below).

```rust
trait Mode7 {
    fn setup(cam: *M7Camera, repeat: M7Repeat, flip: M7Flip); // BGMODE 7, M7SEL, own hardware; follow cam
    fn set_camera(cam: *M7Camera);              // follow another camera from now on
    fn camera() -> *M7Camera;                   // that camera
    fn update();                                // build the next frame from the camera + properties
    fn nmi();                                   // commit the built frame; from the NMI handler
    fn to_screen(x: M7Coord, y: M7Coord) -> i16, i16, u16;   // sx, sy, texel size (8.8 px)
    fn to_world(sx: i16, sy: i16) -> bool, M7Coord, M7Coord; // on the map?, x, y

    fn sel() -> u8;                             // the implementor's M7SEL value
    fn set_sel(sel: u8);

    fn set_repeat(repeat: M7Repeat) { Self::set_sel((Self::sel() & 0x03) | repeat as u8); }
    fn set_flip(flip: M7Flip) { Self::set_sel((Self::sel() & 0xC0) | flip as u8); }
    fn repeat() -> M7Repeat { return (Self::sel() & 0xC0) as M7Repeat; }
    fn flip() -> M7Flip { return (Self::sel() & 0x03) as M7Flip; }
}
```

- **Associated functions, static dispatch.** Every method is called on the
  implementing type (`M7Static::nmi()`), as a direct call. There is no
  `*dyn`: a trait with associated functions can't be one, and the game
  always knows which mode it is in.
- **No state in the trait.** Each implementor keeps its own M7SEL value,
  center, scroll and matrix data. `sel()` and `set_sel()` are the two
  accessors the four defaults are written against, once for every
  implementor ([default method bodies](../../docs/traits.md)).
- **One shape for sprites.** `to_screen` returns the same three values in
  every view: sx, sy, and the on-screen size of one texel there (8.8
  pixels). sy is `M7K_HIDDEN` (0x7FFF) for a point that can't be drawn,
  which only the floor ever returns.
- **No `stop()` in the trait.** Only the HDMA views have anything to
  release, so `stop()` is their own function, not a `Mode7` method; a
  Static view has none. See [Switching modes](#switching-modes).

`M7_CENTER_X` / `M7_CENTER_Y` (128, 112) are the screen center, the usual
pivot.

### M7SEL

M7SEL is described by two enums whose discriminants are its bits, so the
register value is `repeat as u8 | flip as u8`:

```rust
/// What the plane shows beyond its 1024×1024 texels (M7SEL bits 6-7).
enum M7Repeat {
    /// The whole 128×128 tilemap repeats forever in every direction.
    Wrap = 0x00,
    /// Nothing is drawn outside the map, so the backdrop or a lower layer
    /// shows through: a floating island, or a track over the void.
    Transparent = 0x80,
    /// Outside the map, tile 0's 8×8 pattern repeats, and the tilemap
    /// doesn't: an ocean or grass around a finite level, from one tile.
    Tile0 = 0xC0,
}

/// Reflection of the screen (M7SEL bits 0-1).
enum M7Flip { None = 0x00, Horizontal = 0x01, Vertical = 0x02, Both = 0x03 }
```

Hardware value `0x40` (bits 6-7 = 01) also wraps, so it has no variant:
`Wrap` is the one name for it. `impl M7Repeat` adds `fn wraps(self) -> bool`,
which is true only for `Wrap`. The `to_world`s use it.

`Both` is its own variant, not `Horizontal | Vertical`, so a value is
always one of the four reflections and a `match` over it is complete.
`impl M7Flip` adds:

- `fn horizontal(self) -> bool` and `fn vertical(self) -> bool`, which test
  the bits;
- `fn toggle_h(self) -> M7Flip` and `fn toggle_v(self) -> M7Flip`, which
  return the reflection with one axis switched. These are `match` tables,
  not bit arithmetic on an enum.

The hardware reflects the **screen** coordinate before the matrix is
applied: Sx becomes 255 − Sx for Horizontal, and Sy becomes 255 − Sy for
Vertical. The matrix, the center and the scroll don't change. A flip is
therefore free at run time, and it's a separate thing from scaling, which
is why `zx` and `zy` stay unsigned (see [static.r65](#staticr65-m7static)).

The flip is per view: `M7Static::set_flip` and `M7Plain::set_flip` change
different state (a floor's is its transport's), and each `nmi()` writes
its own.

### Register writers

The `nmi()`s share two stateless writers. Each write-twice register gets
its low byte, then its high byte.

- `m7k_write_matrix(a, b, c, d: i16)`: M7A–D.
- `m7k_write_view(sel: u8, cx, cy, hofs, vofs: u16)`: M7SEL, M7X/M7Y and
  BG1HOFS/BG1VOFS.

### Uploads

- `mode7_upload_interleaved!(DATA)` copies 32 KB of interleaved map and chr
  data (an `.md7` blob) to VRAM word 0 in one DMA. It wraps stdlib's
  `dma_copy_vram_const!`.
- `mode7_upload_split!(MAP, CHR)` sends separate map bytes to the VRAM low
  bytes (VMAIN increments on low) and chr bytes to the high bytes (VMAIN
  increments on high), as two DMAs of 16 KB each.

### Fixed-point multiplies

All of mode7kit's multiplies use the SNES 8×8 unit through stdlib's
`#[hw(0x4202)] static mut WRMPY: u16`. WRMPYA and WRMPYB
are adjacent, so one 16-bit store loads both bytes and starts the multiply
(WRMPYB is written last). `NOP(4)` covers the 8-cycle wait, then `RDMPY` is
read. That is about half the cost of a far `mul8` call, and stays in m16.
`#[hw(0x4203)] static mut M7K_WRMPYB: u16` stores WRMPYB alone (its high
byte lands in WRDIVL, which starts nothing), for a second product by the
WRMPYA already loaded.

| Helper | Computes |
|---|---|
| `m7k_abs(v: i16) -> bool, u16` | sign and magnitude |
| `m7k_mul_q8(m, k)` | (m · k) >> 8, exact, for an 8.8 factor m ≤ 2.0, saturating: two multiplies for m's fraction, plus k once or twice for its whole part. Also the lateral stretch, of a row factor, a size or an offset |
| `m7k_smul_q8(m, k)` | the same, signed m, \|m\| ≤ 256 |
| `m7k_rotate14(s, c, dx, dy) -> i16, i16` | A 10.6 offset turned into view space, (forward, right) in texels: eight multiplies inline (`m7k_tprod2!`, four from each of sin and cos, loaded into WRMPYA once), each product's magnitude >> 14, then signed |
| `m7k_smul_shr14`, `m7k_smul_shr8`, `m7k_smul_shr2` | general signed products, bits 14.., 8.., 2.., by sign and magnitude through stdlib's `mul16_wide` |

The full 16×16 → 32 product is stdlib's `mul16_wide(a, b) -> lo, hi`, which
uses the same one-store pairs and skips the partial products of a zero high
byte. mode7kit has no multiply of its own beside it.


### Sin and cos

`core.r65`'s first table:

```rust
const fn m7k_build_sin() -> [i16; 65] {
    let mut t: [i16; 65] = [0; 65];
    for i in 0..65 { t[i] = fixed_sin(i as u16, 256, 256); }
    return t;
}
static M7K_SIN: [i16; 65] = m7k_build_sin();      // 130 B, a quarter turn
```

`fixed_sin` is the builtin `round(sin(2π·i/256)·256)`
(r65/compiler/builtins/registry.py:112). It is exactly symmetric, so the
other three quarters are the quarter's mirror (`64 - (a & 63)` when bit 6
is set) and negation (bit 7): the same values as a full 320-entry table,
in 130 B instead of 640, for a few cycles a lookup. A view reads it a few
times a build.

| Function | Does |
|---|---|
| `m7k_sincos(a: u8) -> i16, i16` | Both, from one fold of the quarter wave: mirrored and negated by `a`'s quadrant, `cos(a) = sin(a + 64)` |
| `m7k_sin(a: u8) -> i16`, `m7k_cos(a: u8) -> i16` | One of them, through `m7k_sincos` |
| `m7k_heading(angle: u8, speed: u8) -> i16, i16` | (−sin, −cos) × speed, as a 10.6 world delta: `speed` is in 1/64 texel, so 64 moves one texel forward. The plane's forward is −Y at angle 0, as in both demos. |

`M7Static` uses the table for its matrix, the floor for its per-line
signs and its projections, and `M7Camera` for movement.

### Zoom reciprocal

`core.r65`'s other table:

```rust
const fn build_recip() -> [u16; 256] {
    let mut t: [u16; 256] = [0; 256];
    t[0] = 0x7FFF;
    for z in 1..256 { t[z] = 16384 / z; }      // 8.8: 64 → 0x0100
    return t;
}
static M7K_RECIP: [u16; 256] = build_recip();     // 512 B
```

The matrix entry is texels per pixel, which is the inverse of on-screen
size. Indexing by a size-linear `zoom` means stepping `zoom` by ±1 a frame
zooms smoothly. Sample values: T[16] = 0x0400 (¼×), T[64] = 0x0100 (1×),
T[128] = 0x0080 (2×), T[255] = 0x0040 (≈4×).

| Function | Does |
|---|---|
| `m7k_recip(zoom: u8) -> u16` | Table read |

`M7Static` uses it for its scale, and the floor for a texel's on-screen
size (`M7K_RECIP[z]` is 1/k in 8.8).

## The camera and world coordinates (core.r65)

`core.r65` holds the camera type and the coordinate helpers the
projections share. It declares no camera: the game does.

### The coordinate type

```rust
struct M7Coord(u16);   // 10.6 fixed-point texels
```

`M7Coord` lives in `core.r65`, since the trait's signatures name it.
`M7Coord` is a newtype, so it's nominal: an `M7Coord` never mixes up with
a screen pixel or a whole-texel `u16` without an `as` or `.0`. It still
passes in a register and inherits `+` and `-` from its payload.

10.6 is chosen because the plane is 1024 texels, which is exactly 65536
sixty-fourths. Plain u16 arithmetic therefore **is** the Repeat wrap:
`x + step` past texel 1023 lands back at texel 0 with no `& 0x3FF`. And
`(a − b) as i16` is the shortest wrapped distance between two points,
±512 texels, again with no wrap code. Every projection below starts from
that difference.

| Item | Does |
|---|---|
| `M7Coord::from_texel(t: u16) -> M7Coord` | `t << 6` |
| `c.texel() -> u16` | `c.0 >> 6` (0..1023) |
| `c.tile() -> u8` | `c.0 >> 9` (0..127) |
| `m7k_delta(a: M7Coord, b: M7Coord) -> i16` | `(a.0 − b.0) as i16`, the wrapped difference in 10.6 |
| `m7k_tile_index(x: M7Coord, y: M7Coord) -> u16` | `(y.tile() << 7) \| x.tile()`, the index into a 128×128 map. The game reads its own map (`MAP[i]`) for collision and terrain. mode7kit doesn't hold a copy. |

### The world camera

```rust
struct M7Camera {
    x: M7Coord, y: M7Coord, heading: u8,
    scale_x: u8, scale_y: u8, height: u8, pitch: i8,
}

// the game's: m7k_camera(x, y) is that literal, at texel (x, y), facing
// heading 0, at scales 64, 64 (1×), height 128 and pitch 0
#[lowram]
static mut CAMERA: M7Camera = m7k_camera(512, 512);
M7Plain::setup(&CAMERA, M7Repeat::Wrap, M7Flip::None);
```

The methods take `*self`, so a game may have several cameras
(`#[lowram] static mut CAM_B: M7Camera = ...`):

| Method | Does |
|---|---|
| `set(x: M7Coord, y: M7Coord)`, `get()` | Position |
| `set_heading(h: u8)`, `heading()` | Heading, 256 per turn; 0 looks toward −Y |
| `turn(d: i8)` | Adds to the heading |
| `set_scale(x: u8, y: u8)`, `scale()` | The zoom on each screen axis, in the matrix zoom's unit: 64 is 1×, higher is closer (below) |
| `set_height(h: u8)`, `height()` | Texels above the plane, for the perspective views (below) |
| `set_pitch(p: i8)`, `pitch()`, `tilt(d: i8)` | Pitch, −32..64 (`tilt` keeps it there). Each view reads it its own way: `M7Plain` as a horizon shift in scanlines (positive looks up), `M7PlainRotation` as an angle (6..64, 64 straight down). `M7Static` ignores the pitch. |
| `forward(speed: i16)` | Moves `speed` 1/64 texels along the heading (`m7k_heading`, in steps of at most 255, so any `i16` moves its full distance); negative moves back |
| `strafe(speed: i16)` | Moves across the heading, toward the screen's right (`m7k_heading(angle − 64)`); negative moves left |
| `move_by(dx: i16, dy: i16)` | Adds a 10.6 delta. Wraps for free. |

**Scales and a height.** The camera holds what each view reads, in the
form it can use with the least work. `M7Static` builds a matrix every
`update()` and has no height, so the scales are its matrix zooms as they
are, through `M7K_RECIP`: no conversion, and a stretch for free. A
perspective view needs an altitude and a lateral stretch:

- **H = height · 64 / scale_y** texels. This is the pinhole identity:
  zooming the world in by k around the point under the camera shows what
  a camera k times lower sees, so a scale zooms a perspective view as it
  zooms `M7Static`, and the height is its own knob on top.
- **q = scale_y / scale_x** (8.8) stretches the lateral factors, A and C,
  and **p = scale_x / scale_y** the projections' lateral sizes and
  offsets. `m7k_lateral` clamps scale_x to just over half and at most
  twice scale_y, so q < 2 and a lateral factor, at most 128·q, fits its
  byte.

Both divide (`div16`), so a view computes them only when a scale or the
height changes; it rebuilds its line tables or rows then anyway, and each
frame it compares three bytes with the ones it built for. A new stretch
bumps `gen`, so the rows' keys miss. At height 128 a straight-down
`M7PlainRotation` shows `M7Static`'s picture for the same scales (a test
checks it to within z's rounding).

Each perspective view clamps H to the altitudes its tables hold.
`M7Plain`'s 128 floor heights are H = 40 + h/2, 40..103.5 texels, and
`m7k_row_height(height, sy)` is h = height · 128 / sy − 80, clamped.
`M7PlainRotation` takes H itself, 40..248: under 40 the near lines' depth
scale runs past `M7K_ZRECIP`, and over 248 it nears a byte's end.

A stretch costs `M7Plain` more. Its rows share one product between A and
D (A = D, C = −B), two products a row; unequal scales make A ≠ D, so a
stretched floor takes `core.r65`'s four-product rows (`m7k_rows4!`, the
plain rotation's loop at sin θ = 1), chosen once a build, and the
two-product loops stay for equal scales. `M7PlainRotation` already takes
four products a row; the stretch only scales its two lateral factors,
once a build.

**The game owns the cameras.** `Mode7::setup(cam, repeat, flip)` takes
one, so a view can't be set up without it: forgetting is a compile error,
not a read through a null pointer.
`set_camera(&cam)` swaps it later. A view's `update` (and a scan view's
`build`) does nothing until it has a camera, so a view used before its
`setup` stays blank instead of reading a camera from $0000. Two views set up with one camera show
the same place, so switching between `M7Static` and a floor keeps the
view where it was. A view keeps
the pointer in its state, not a copy, so the game moves the camera and the
next `update()` follows. The pointer is near, so a camera must be a
`#[lowram]` static (a `#[ram]` one's address is far and won't type-check).
Two floors take a camera each. A negative speed turns the heading a half
turn rather than negating the delta.

**Sub-texel camera.** The Mode 7 registers take whole texels only, so the
picture moves in whole-texel steps. When zoomed in 4×, a slowly moving
camera steps 4 px at a time. Projection therefore measures objects from the
**whole-texel** camera, `cam & 0xFFC0`, the same one the registers show.
Sprites then stay locked to the ground instead of drifting ahead of it by
the dropped fraction. Each object keeps its full 1/64-texel position, so
objects themselves move smoothly.

The projections measure from the whole-texel center with
`m7k_from_center(x, y, cx, cy)`, given the center the mode last built.

### Repeat modes and range

| `M7Repeat` | World | `m7k_delta` | `to_world` / tile lookup |
|---|---|---|---|
| `Wrap` | a torus, 1024 texels around | the shortest way round, ±512 texels: an object 600 texels east really is 424 texels west | always lands on the map |
| `Transparent` | the map, with nothing beyond it | exact while objects are within 512 texels of the camera | can land off the map, which is empty |
| `Tile0` | the map, inside an endless field of tile 0 | same as `Transparent` | off the map it is tile 0 |

The difference is only wrong without wrapping, for an object more than
half the plane away. That object is off screen at any zoom of ¼× or more,
since the screen spans at most 1024 texels.

A 10.6 coordinate can't tell "texel 1020" from "4 texels west of the map",
because both are the same u16. So when the plane doesn't wrap, the world
functions report the edge separately:

- `to_world(sx, sy) -> bool, M7Coord, M7Coord`, in every view. The `bool` is
  *on the map*: always true under `Wrap`. Otherwise it's false when the
  unwrapped camera-plus-offset falls outside 0..1023 on either axis, which
  is checked on the i16 offset before it's added (`m7k_on_map`). The
  floor's `to_world` also returns false above the horizon.
- The map lookup stays with the game, through `m7k_tile_index`. When the
  flag is false, a game using `Tile0` reads tile 0 instead, and one using
  `Transparent` treats the spot as a hole, such as falling off a track.

## static.r65: `M7Static`

Static mode: one matrix a frame, committed in vblank.

```rust
struct M7Static {
    sel: u8,                                // M7SEL
    a: i16, b: i16, c: i16, d: i16,         // M7A..D, 8.8
    ia: i16, ib: i16, ic: i16, id: i16,     // the inverse, for the projections
    cx: u16, cy: u16, hofs: u16, vofs: u16,
    px: u8, py: u8,                         // the pixel the camera is pinned to
    zoom: u8,                               // the last matrix's horizontal zoom, 64 = 1.0
    camera: *M7Camera,
}
#[lowram]
static mut M7K_STATIC: M7Static = /* identity, center (128, 112), zoom 64 */;
```

The inverse is kept next to the matrix for the projections. No runtime
division ever computes it: each function that writes the matrix also writes
its inverse, which costs that function almost nothing. Only `set_matrix`
cannot do this, so the caller passes the inverse to it (`set_inverse`), or
simply doesn't project.

| Function | Does |
|---|---|
| `setup(cam, repeat, flip)` | Follows `cam`; BGMODE = 7, and M7SEL with its copy. Call in force blank, or in vblank when switching modes. The game still owns TM. |
| `update()` | `rotate_scale(heading, scale_x, scale_y)` with the camera's scales, then pins the camera's texel to `(px, py)`: center = camera, hofs = cx − px, vofs = cy − py. |
| `nmi()` | `m7k_write_matrix`, then `m7k_write_view`. Never writes HDMAEN. |
| `to_screen`, `to_world` | The flat projection below. `size` is `zoom << 2`, the horizontal texel size; sy is never `M7K_HIDDEN`. |
| `set_pivot(sx, sy)` | The pixel `update()` pins the camera to |
| `zoom()` | The horizontal zoom of the last matrix built (`update`, `scale`, `rotate_scale`, `identity`) |
| `rotate(angle)`, `scale(zx, zy)`, `rotate_scale(angle, zx, zy)`, `identity()`, `set_matrix(a, b, c, d)`, `set_inverse(ia, ib, ic, id)`, `set_center(cx, cy, hofs, vofs)` | Manual control, for a game that doesn't call `update()` |

**No HDMA.** Static mode never writes HDMAEN or any DMA register: a Static
game owns HDMAEN outright and may run its own HDMA on any channel.

### The matrix

Rotation matrix: Mode 7 maps a screen pixel to a texel with

```
Tx = A·(Sx + HOFS − X0) + B·(Sy + VOFS − Y0) + X0
Ty = C·(Sx + HOFS − X0) + D·(Sy + VOFS − Y0) + Y0
```

A = cos, B = sin, C = −sin, D = cos rotates the view around (X0, Y0), which
`update` places at the camera.

`rotate` is A = D = cos, B = sin, C = −sin, with the inverse Rᵀ: ia = id =
cos, ib = −sin, ic = sin. `scale` is A = T[zx], D = T[zy], B = C = 0, with
ia = zx << 2, id = zy << 2 (zoom/64 in 8.8). Neither multiplies.

`update()` zooms by the camera's scales, `scale_x` as `zx` and `scale_y`
as `zy`.

The manual setters take a zoom per axis: `zx` scales the **horizontal
screen axis** and `zy` the **vertical**. In
the matrix, A and C are the texel step per screen pixel in x, and B and D
the step per screen line. A uniform zoom passes the same value twice.
Unequal values give:

- squash and stretch effects;
- pixel-aspect correction. SNES pixels are 8:7, wider than tall, so
  `rotate_scale(a, 56, 64)` (or the camera's `set_scale(56, 64)`) shrinks
  the horizontal axis and makes a square texel look square on a 4:3
  display;
- a pseudo-tilt: a smaller `zy` foreshortens the plane vertically. This is
  a cheap stand-in for a top-down camera tilted back, without the per-line
  cost of perspective.

`M7Static::rotate_scale(angle: u8, zx: u8, zy: u8)` composes the scale in
**screen space**, after the rotation. The picture is rotated first, and
then stretched along the screen's own axes. Stretching the world's axes
before rotating would make the stretch spin with the map, which is rarely
what a game wants:

```
M  = R · diag(1/sx, 1/sy)

kx = M7K_RECIP[zx]   ky = M7K_RECIP[zy]    // u16 8.8, ≤ 0x7FFF
A  =  (cos · kx) >> 8      B = (sin · ky) >> 8
C  = −(sin · kx) >> 8      D = (cos · ky) >> 8
```

When `zx == zy`, A = D and C = −B, so the function takes a 2-multiply path.
Otherwise it does all 4.

`cos` and `sin` are signed, with |v| ≤ 256. They're multiplied by sign and
magnitude with `m7k_smul_q8`: two 8×8 multiplies (k's low and high byte
times |v|), the sign applied afterward, saturating to ±0x7FFF.

The inverse is diag(sx, sy)·Rᵀ, with sx = zx/64:

```
ia =  (cos · zx) >> 6      ib = −(sin · zx) >> 6
ic =  (sin · zy) >> 6      id =  (cos · zy) >> 6
```

These are 9-bit × 8-bit products, 2 of them when the zooms are equal and 4
otherwise. A frame therefore costs 4 to 8 multiplies.

### Flat projection

These use `M7Static`'s matrix and inverse. They give the right answer
whichever of `update`, `rotate`, `scale`, `rotate_scale` or `set_matrix` +
`set_inverse` set the matrix.

```
world → screen:  S = P + M⁻¹ · (W − C)
screen → world:  W = C + M  · (S − P)
```

P is the pivot (`set_pivot`), C is the whole-texel camera and W is the world
point. M⁻¹ is (ia, ib / ic, id).

| Function | Does |
|---|---|
| `M7Static::to_screen(x: M7Coord, y: M7Coord) -> i16, i16, u16` | dx, dy = `m7k_delta` from the camera (10.6, ±32767). sx = px + ((ia·dx + ib·dy) >> 14), and sy the same way with ic and id. The `>> 14` drops 8.8's 8 bits and 10.6's 6 bits, so sub-texel object positions reach the screen. Then the reflection: sx becomes 255 − sx if `flip().horizontal()`, and sy becomes 255 − sy if `flip().vertical()`. The size is `zx << 2`. |
| `M7Static::to_world(sx: i16, sy: i16) -> bool, M7Coord, M7Coord` | First undoes the reflection the same way, then computes dx = a·(sx − px) + b·(sy − py) and dy = c·(sx − px) + d·(sy − py), both 8.8 times pixels (texels·256). A `>> 2` gives 10.6, which is then added to the camera. The `bool` says whether the point is on the map (see [Repeat modes](#repeat-modes-and-range)). Used for picking and for "what's under this pixel". |

The reflection is a subtraction from 255 on each side, so sprites placed
through `to_screen` follow a flipped floor with no extra multiply. The
hardware mirrors around the screen center, whatever the pivot. `px` and `py`
stay as `set_pivot` gave them, in the unreflected screen, so with a horizontal
flip the camera point appears at 255 − px. With the default center pivot it
stays where it was.

Each of these is 4 signed multiplies (`m7k_smul_shr14` / `m7k_smul_shr2`),
done by sign and magnitude through `mul16_wide`. The
results aren't clipped: a point off screen just has coordinates outside
0..255 / 0..223, and the game decides whether to draw it.

## hdma.r65: the transport

`m7k_hdma!` writes the transport: one Mode 7 matrix a scanline by indirect
HDMA, double-buffered, with no math. A per-line view or a custom effect
fills its rows; `commit()` shows them. `hdma.r65` holds the macro, the
HDMA table writers it uses, and the default instance `M7HDMA`, which the
per-line views include; `core.r65` has none of it, so a Static-only game
never sees it. Include-once keeps `M7HDMA` single when both views are in
one ROM: their files can't each invoke the macro, or it would be declared
twice. It writes HDMAEN, from a shadow other layers
add their channels to, and M7SEL and the view (M7X/M7Y, BG1HOFS/VOFS)
with each frame it shows.

```rust
struct $name {
    sel: u8,                                // M7SEL as the game set it
    cx: u16, cy: u16, hofs: u16, vofs: u16, // the view, for the frame being built
    back: u8, ready: u8,                    // the buffer being built; set by finish
    hdmaen: u8,                             // HDMAEN shadow: the matrix channels and others'
    floor: bool,                            // the frame is a floor: drop M7SEL's vertical bit
    top: [i16; 4],                          // the matrix outside the rows: AB unit, CD unit
    abi: [u8; 64], cdi: [u8; 64],           // indirect tables, 32 bytes a buffer
    ab: [i16; $lines * 4],                  // rows, both buffers: [2·lines·k + 2r] = A, [+1] = B
    cd: [i16; $lines * 4],                  // [2·lines·k + 2r] = C, [+1] = D
    stamp: [u8; 2],                         // per buffer: bumped by writes keys can't see
}
#[ram]
static mut $state: $name = /* identity top, all zero, sel 0 */;
```

| Function | Does |
|---|---|
| `setup(repeat, flip)` | BGMODE 7, M7SEL, the two channels (DMAP $43: indirect, two write-twice registers; BBAD $1B and $1D; A1B and DASB `M7K_RAM_BANK`), both buffers' tables to the top matrix, both stamps bumped, the channels in the shadow |
| `stop()` | Takes the channels out of the shadow and writes HDMAEN at once, since the handler no longer commits |
| `commit() -> bool, u8` | From the NMI handler: see [Double buffer and commit](#double-buffer-and-commit) |
| `sel()`, `set_sel(sel)` | M7SEL |
| `enable(mask)`, `disable(mask)` | Others' channels in the HDMAEN shadow |
| `back_index() -> u8`, `back() -> u16`, `stamp() -> u8` | The buffer being built: its number, its first element in `ab`/`cd`, its stamp |
| `set_line(row, a, b, c, d)`, `set_top(a, b, c, d)`, `set_center(cx, cy, hofs, vofs)` | The per-line layer: a row, the top matrix, the view |
| `publish(top, rows)` | A custom frame: lines 0..top hold the top matrix, line top + r reads row r, and the table ends after them |
| `begin()`, `seg_top(p, lines)`, `seg_rows(p, row, lines)`, `seg_hold(p, row, lines)`, `finish(p, floor)`, `finish_same(floor)` | A frame of several segments, for a game stacking views: the top matrix, rows one a line, one row held |
| `LINES` | The rows a buffer holds |

### The `Mode7Scan` trait

`core.r65` also declares the trait a per-line view implements on top of
`Mode7`. It knows nothing of skies or horizons: a build renders rows into
a region of lines, `band()`, and the lines above it, down from the
build's `top`, show the transport's top matrix. That is all a game needs
to put a band over the lines above one, or to stack two in a split,
without knowing how it computes its rows.

```rust
trait Mode7Scan: Mode7 {
    fn build(top: u8, lines: u8);   // rows, center, scroll into the back buffer; no publish
    fn publish();                   // the last full-screen build as the next frame
    fn band() -> u8, u8;            // the region: its first screen line, and its line count
    fn segment(p: u16) -> u16;      // append that region's segments at cursor p
    fn center() -> u16, u16;        // its M7X, M7Y
    fn scroll() -> u16, u16;        // its M7HOFS, M7VOFS
}
```

`m7k_plain!` implements it: `band()` is its horizon and the lines from
there to the bottom of its band. The flyer's sky and the split example call only `Mode7` and
`Mode7Scan` methods on their floors, and read a sky's parallax from the
floor's `camera()`, so another floor (a true pitch, a game's own effect)
that implements both drops in by name. An NMI handler that shows add-ons
with the frame calls the transport's `commit()` itself.

### Shared scan-view code

`M7Plain` and `M7PlainRotation` differ in their line tables, their rows'
products, their sky and pivot, `to_world`'s forward distance (the floor's is
exact, from (foot − l)·z; `M7PlainRotation` reads its table) and `segment`. The
rest is one body in `core.r65`, as macros each instance expands in its own
functions, so the code stays the instance's, on absolute addresses, at no
run-time cost (the bench didn't move).

`m7k_scan_view!(Name, STATE, Hdma, HDMA_STATE, {build}, {segment},
{forward})` writes everything else of a view: its `impl Mode7` and `impl
Mode7Scan`, `stop` and `depth`. The three blocks are the parts that differ:
`build(top, lines)`'s body, `segment(p)`'s, and `to_world`'s forward offset
(`m7k_fs`, `m7k_fc`: the distance on line `l` times the heading's sin and
cos, in 10.6). A block passes through as a function body, so a view's own
code costs no call. The view's macro keeps only its state struct, its
initializer and its `rebuild_lines`. The other macros:

| Macro | Body of |
|---|---|
| `m7k_scan_camera!(STATE, cam)` | `build`'s start: the scales and height against the ones last read, the stretch on a scale change; leaves `m7k_sy`, `m7k_ch`, `m7k_new_h`, `m7k_fresh` for the view's altitude |
| `m7k_scan_to_screen!(STATE, HDMA_STATE, x, y)` | `to_screen`: the cull by `reach`, `m7k_rotate14`, the signed search of `line_dist`, sx from `M7K_RECIP` |
| `m7k_scan_build_rows!(STATE, Hdma, HDMA_STATE, rows, cam, top, n)` | `build` after the band and `pivot`: the heading, the keyed rows, the center and the scroll (vofs = cy − pivot) |
| `m7k_scan_publish!(Name, STATE, Hdma)` | `publish`: the top matrix to the horizon, then `Name::segment`, unless the buffer's tables match |

They need the same state fields in both, named in `core.r65`'s comment:
the band, `pivot`, the heading, the view, `line_z`, a signed `line_dist`,
`reach`, `gen` and the keys. The row builders take the same arguments
(`M7PlainRotation`'s reads its `sin_t` from its state), so the build tail calls
either.

### HDMA layout

DMAP $43 is transfer mode 3 (two write-twice registers, 4 bytes) in
indirect mode: each channel's table is a list of (count, address) entries,
and the 4-byte units they point at are the `ab` and `cd` rows. A
continuous entry reads a new unit every line; a once entry holds one unit
for its lines.

A floor's frame looks like this:

```
sky (once)                  → &top[0]   (AB)   / &top[2] (CD)
0x80 | 127 (continuous)     → &ab[2·lines·k]
0x80 | ground − 127         → &ab[2·lines·k + 254]     // 127 rows × 2 words
0
```

The lines above the horizon cost nothing to build: one entry holds the
top matrix. A table has room for 10 entries in its 32 bytes; a floor uses
at most 4, a split screen 6. After the last entry the channel stops, and
M7A–D keep the last row's values, which no line in another BG mode reads:
that is how a HUD band below the floor works.

Rows are the transport's, not the screen's: a segment names the row it
starts reading from. A floor writes its ground lines from row `top`, its
band's first line, so pitch, which only moves the horizon within the band,
changes the tables and not the rows.

### Double buffer and commit

- **`finish` is the last step,** and the only thing that sets `ready`. A
  builder writes its rows and segments, then `finish(p, floor)` ends both
  tables and marks the back buffer ready. An NMI never sees a half-built
  frame.
- **`commit() -> bool, u8`**, from the NMI handler. If `ready`, it points
  A1Tn at the finished buffer's tables, flips `back`, clears `ready`, and
  writes M7SEL (without the vertical bit for a floor), the center and the
  scroll with `m7k_write_view`. It always writes HDMAEN from the shadow,
  and never M7A–D. It returns whether it flipped and the buffer now shown.
- **Add-ons follow the front buffer.** A game's own per-line add-on (the
  examples' bands and views) double-buffers its tables with the
  transport's `back_index()`, and in the NMI handler, after `commit()`,
  points its channels at the buffer now shown: the one `commit()` returns,
  or `back_index() ^ 1` every frame. No add-on reads the transport's
  fields. All of it runs in vblank, and HDMA reloads A1Tn at
  the top of a frame, so the channels never disagree on screen.
- **The view follows the tables.** The view is written only on a frame
  that flips, so it never pairs with the other buffer. If a build doesn't
  finish before vblank (a lag frame), the old picture stays whole.

### Build keys

Each buffer records what it holds, so a builder skips what would come out
the same:

| Part | Key per buffer | Kept by |
|---|---|---|
| a floor's rows | heading, line-table generation, band top, rows built, the transport's stamp | the floor |
| a floor's tables | horizon, ground lines, stamp | the floor (`finish_same`) |

The two buffers alternate, so a change rebuilds two frames in a row, and a
steady view then costs the comparisons. A custom `publish` and `setup`
bump the stamp, so a floor never keeps rows a game wrote over. Flying
straight changes no row: the rows depend on the heading and the line
tables and the stretch, and translation moves only the view.

### The per-line layer

For an effect that isn't a floor (ripples, a curved horizon, a stretch), a
game drives the transport itself:

```rust
let mut r: u8 = 0;
while r < 224 { M7HDMA::set_line(r, a, b, c, d); r++; }
M7HDMA::set_center(cx, cy, hofs, vofs);
M7HDMA::publish(0, 224);
// in the NMI handler: let _flipped, _k = M7HDMA::commit();
```

`set_line` is a far call with five arguments: fine for a few rows. A
full-screen effect can write `$state.ab` / `$state.cd` from `back()`
directly, as the floor does. `tests/options/` runs one.

### HDMA table writers

- `m7k_hdma_ind(t, pos, lines, addr: u16, unit: u16, continuous: bool) -> u16`
  writes ≤127-line indirect entries; a continuous entry after the first
  starts 127 units further on.
- `m7k_hdma_hold(t, pos, lines, value: u8) -> u16` writes ≤127-line direct
  once entries of a byte.
- `m7k_hdma_end(t, pos)` ends a table.

HDMA header semantics: bit 7 = 0 means **once** (one unit is transferred on
the entry's first line and the register holds it). Bit 7 = 1 means
**continuous** (a new unit every line). Bits 0–6 are the line count, and
mode7kit keeps it at 1..127.

## plain.r65: the perspective floor

`m7k_plain!` writes a floor: the Mode Y ground of dizworld's working main
loop (dizworld.r65:1279–1533), following one camera, building its rows into
a transport, and projecting. It implements `Mode7`. Compared with
dizworld:

1. It has **no runtime division**: dizworld's per-frame divisions are
   moved into per-height tables.
2. It is **indirect HDMA over typed rows**, so a line costs four 16-bit
   stores, not eight byte stores and headers.
3. It is **double-buffered and keyed**, so HDMA never reads a half-built
   table, and an unchanged view costs nothing.

```rust
struct $name {
    top: u8, sky: u8, ground: u8,           // the last build's band top, horizon (screen line), ground lines
    foot: u8, built_sy: u8,                 // the line tables' foot and camera scale_y (0: none)
    sin: i16, cos: i16,                     // the last build's heading
    depth: i16,                             // the last projected point's
    cx: u16, cy: u16, hofs: u16, vofs: u16, // the last build's view
    line_z: [u8; 224], line_dist: [i16; 224],
    key_*: [u8; 2],                         // per buffer: see Build keys
    camera: *M7Camera,
    gen: u8, pivot: u16, reach: u16,        // table rebuilds, the pivot line, the cull distance
    key_tgen: [u8; 2],
    row: u8,                                // the line tables' floor height, 0..127
    built_sx: u8, built_h: u8,              // the camera's scale_x and height, as last read
    lat: u16, lat_px: u16,                  // the lateral stretch, texels/pixel and its inverse (8.8)
}
#[ram]
static mut $state: $name = /* no tables built */;
```

| Function | Does |
|---|---|
| `setup(cam, repeat, flip)` | Follows `cam`; the transport's setup; the keys cleared |
| `stop()` | The transport's stop |
| `update()` | `build(0, LINES)`, then `publish()` |
| `nmi()` | The transport's `commit()` |
| `to_screen`, `to_world` | The floor projection, [below](#world-projection) |
| `sel()`, `set_sel()` | The transport's |
| (the camera's scales, height and pitch) | Read by the build. The floor height (`m7k_row_height`, clamped to 0..127) and the stretch (`m7k_lateral`) divide, so the build computes them only when the scales or the height change, and rebuilds the tables only when the floor height does; the pitch is clamped to −32..64 |
| `depth()` | The last projected point's depth |
| `band()`, `center()`, `scroll()` | `Mode7Scan`: the last build's rows (the horizon and the lines to the band's bottom) and view |
| `build(top, lines)` | `Mode7Scan`: the band of `lines` lines from screen line `top`: its rows, from row `top`, and its view; no publishing |
| `publish()` | `Mode7Scan`: a full-screen frame of the last build: the top matrix down to the horizon, then the rows |
| `rebuild_lines(h)` | The line tables for floor height h (0..127); the build calls it when the height changes |

**Bands.** `build(top, lines)` puts the horizon at `top + sky`, the sky
clamped to the band, and builds `lines − sky` ground lines. A band
shorter than the screen is **cropped, not rescaled**: it keeps the full
screen's geometry, the horizon 32..95 lines down and the foot below the
screen, and shows the band's lines of it. A 112-line band shows the
horizon and the far ground, as though the camera sat further back; looking
down a little shows more floor. Per-band geometry would need the
`M7K_ROW_*` tables for each band height (see [Limits](#limits-and-future-work)).

### Tables

`M7K_ZRECIP: [u8; 2321]` (in `core.r65`, shared with `M7PlainRotation`)
is dizworld's `build_z_table`:
`T[0] = 255`, and `T[i] = min(255, 32768 / i)`. The index is `zr >> 4`.
At dizworld's near edge `zr` reaches `2^21 / s1_min = 2^21 / 64 = 32768`
(index 2048); the ramp runs 32 lines further for [pitch](#pitch), to index
2320 at height 0. dizworld's 4096-entry table only ever used its first
half.

Three tables indexed by height, `M7K_ROW_SKY: [u8; 128]`,
`M7K_ROW_ZR0: [u16; 128]` and `M7K_ROW_STEP: [u16; 128]` (640 B), apply
dizworld's formulas at compile time. Separate tables rather than an array
of a 5-byte struct: no stride multiply, and simpler const fns. 2^21 doesn't
fit a u16, so `m7k_pow2_div` divides it by long division.

```
h7          = height >> 1                  // 0..63
sky_lines   = 32 + h7                      // 32..95  (horizon scanline)
ground      = 224 − sky_lines              // 129..192, before pitch
s0          = 384 + 2·height               // view depth at horizon
s1          = 64 + h7                      // view depth at near edge
zr0         = 2^21 / s0
zr1         = max(2^21 / s1, zr0)
zr_step     = (zr1 − zr0) / ground
```

This deletes `umul16`, `udiv32_16` and the three 32/16 divisions dizworld ran
every frame.

### Per-line matrix

The depth scale z of each line depends on the height alone, so
`rebuild_lines` computes it, into `line_z`, only when the height changes.
Line l counts down from the horizon, over `foot` lines (see
[Pitch](#pitch)):

```
zr   = zr0 + l·zr_step                     // accumulated, no multiply
z(l) = M7K_ZRECIP[zr >> 4]                 // depth scale
```

Each frame the heading changed, for each ground line `l` in `0..ground`:

```
ma   = (z · cos7) >> 5                     // cos7 = |cos| >> 1  (1.7)
mb   = (z · sin7) >> 5                     // sin7 = |sin| >> 1
A = D = ±ma        B = ±mb        C = −B
```

The signs follow the rotation quadrant, exactly as in dizworld: A = D keeps
the matrix a rotation and scale, not a reflection, and C = −B. The camera
is set as in dizworld, with the pivot on the foot: center = (cam_x,
cam_y), hofs = cam_x − 128, vofs = cam_y − (horizon + foot). The zero
crossing of the vertical term then sits below the band, so every ground
line samples ahead of the camera.

**The row builder** is a macro a floor instance names, expanded in its
build: `m7k_rows_mul`. It is one loop per sign quadrant, so a row applies
no sign: each quadrant's loop computes its A, B and C from the magnitudes
with the signs written in (`0 − ma`, or `ma`). The first product is one
16-bit store, `WRMPY = z | cos7 << 8`, which loads WRMPYA and WRMPYB
and starts it. WRMPYA keeps z, so the second is one store of the sin byte
to WRMPYB alone (`M7K_WRMPYB`, a word at $4203 whose high byte lands
harmlessly in WRDIVL). The A and D stores fill the second product's
8-cycle wait. The loop stays in m16.

**A ROM product tier was tried and dropped.** A table of (z · c) >> 5 for
every c in 0..128 and z in 14..255 is 62,436 bytes, one HiROM bank, and
replaces each multiply and its shift with a table read. Measured on the
bench, the floor on it was slower (165 scanlines turning, against 143):
in the code R65 generates, a read indexed by `row + z` costs what the
multiply's store, wait and read cost, since both go through stack
temporaries. It would pay with the index kept in a register.

### Pitch

The floor reads the camera's `pitch` as scanlines. Positive looks up, so
the horizon moves down the screen; negative looks down.

**Model: a y-shear.** Tilting a pinhole camera by a small angle θ moves its
image vertically by about f·tan θ. A pitched floor is therefore the
unpitched floor moved p lines. This is the look-up/look-down of Doom-era
engines. It is close for small angles, and it inherits the A = D
approximation the floor already makes. An exact pitched camera needs
A ≠ D, 4 multiplies a row instead of 2: that is
[`M7PlainRotation`](#plain_rotationr65-m7plainrotation-a-plain-at-a-true-pitch),
a second view rather than a mode of this one.

**No extra work per line.** Line l counts down from the horizon, so
z(l) and dist(l) are the same at every pitch. `rebuild_lines` still runs
only when the height changes, and pitch only moves the split and the
pivot:

```
p      = clamp(pitch, −M7K_PITCH_DOWN, M7K_PITCH_UP)   // −32..64
sky    = 32 + height/2 + p                             // horizon: 0..159
ground = 224 − sky                                     // lines built: 65..224
foot   = (192 − height/2) + M7K_PITCH_DOWN             // horizon → the point under the camera, lines
vofs   = cam_y − (top + sky + foot)                    // the matrix pivots on the foot
dist(l) = z(l) · (foot − l) / 64
```

Only the number of ground lines follows the pitch, and the build's cost
with it: at the flyer example's height 64, 160 lines at pitch 0, 192
looking fully down and 96 fully up (see [Cycle budget](#cycle-budget)).
Since the rows count from the band's top, a pitch change alone rewrites the
indirect tables, not the rows.

**The foot sits 32 lines below dizworld's.** The foot is the row where the
forward distance reaches zero, the point straight under the camera.
dizworld puts it at screen row 224, just below the screen. Looking down
would lift it into the picture, and the lines under it would sample behind
the camera. So mode7kit puts it `M7K_PITCH_DOWN` = 32 lines lower, which is
the room looking down needs. At pitch 0 the horizon is where dizworld has
it, but every line sees z(l)·32/64 texels farther: at height 64, 384
instead of 320 texels at the horizon, and 12 instead of 0 at the bottom
line. The floor looks somewhat deeper than dizworld's. (The alternative,
dizworld's foot with a floor that can only look up, was turned down.)

`rebuild_lines` fills `foot` lines, as many as a full look down shows. The
ramp then runs 32 lines past dizworld's near edge, which is why
`M7K_ZRECIP` reaches index 2320. `band()` starts at the horizon, so a sky
band set from it moves with the pitch.

### World projection

The floor has no single matrix. Each line has its own scale, k(l) = z(l)/64
texels per pixel, where z(l) is the `M7K_ZRECIP` value on that line. So
the floor has its own `to_screen` and `to_world`, built from the two line
tables `rebuild_lines` fills:

```rust
line_z: [u8; 224],       // z(l), an M7K_ZRECIP byte
line_dist: [i16; 224],   // forward distance seen on line l, texels (signed, as `M7PlainRotation`'s)
```

On ground line l (screen y = horizon + l), the matrix maps the screen
offset (sx − 128, sy − (horizon + foot)) through k(l)·R. The point sampled
at screen-x 128 is therefore straight ahead at

```
dist(l) = k(l) · (foot − l) = z(l) · (foot − l) / 64
```

That depends on height but not on heading or pitch, so `rebuild_lines`
fills it with `line_z`, only when the height changes; its multiply is a
`WRMPY` store of z and the lines left to the foot.

`to_screen(x: M7Coord, y: M7Coord) -> i16, i16, u16`:

1. dx, dy = the 10.6 offset from the whole-texel center
   (`m7k_from_center`).
2. **Cull.** A point further than the horizon's distance on either axis is
   further along the view too: hidden, with no multiply.
3. Rotate into view space with forward = (−sin, −cos) and right =
   (cos, −sin), the same axes as the HDMA matrix:
   f = −(dx·sin + dy·cos), r = dx·cos − dy·sin, in whole texels.
   `m7k_rotate14(sin, cos, dx, dy)` does the four products inline: eight
   8×8 multiplies, each product's magnitude shifted right 14 and then
   signed.
4. If f ≤ 0 the point is behind the camera; if f > dist(0) it is beyond
   the horizon, and if f is under the band's last line's distance it is
   below the band: sy = `M7K_HIDDEN` (0x7FFF).
5. Binary-search `line_dist`, which falls from the horizon down, for the
   line l whose distance is nearest below f. That's 8 compares and no
   multiply, giving sy = horizon + l.
6. sx = 128 ± (|r| · `M7K_RECIP[z(l)]`) >> 8, bits 8..23 of `mul16_wide`.
   `M7K_RECIP[z]` = 16384/z is 1/k in 8.8, `core.r65`'s zoom reciprocal
   table.
7. The third result is `M7K_RECIP[z(l)]`, the on-screen size of one texel in
   8.8. The game uses it to pick a sprite size or a scaled frame. f, kept
   for `depth()`, is the depth for sorting objects back to front.

`to_world(sx: i16, sy: i16) -> bool, M7Coord, M7Coord`: if sy is above the
horizon or below the band, or sx more than 128 pixels from the center
column, it returns the camera and `false`. Otherwise it takes l = sy −
horizon and k = z(l)/64, and computes offset = k·(sx − 128)·right +
k·(foot − l)·forward. That's 2 scale multiplies and 4 trig multiplies,
added to the camera. The `bool` is false when the point is above the
horizon, or off the map under a repeat mode that doesn't wrap, as for
`M7Static::to_world`.

**Reflection.** `Horizontal` works on the floor. It mirrors the view left
for right, and `to_screen` / `to_world` apply 255 − sx as in the flat
case. `Vertical` doesn't. The per-line matrices are chosen by the real
scanline, while the hardware would sample the plane at 255 − Sy, so the
floor and any per-line band would come apart. `commit()` therefore writes M7SEL
without the vertical bit for a floor. The bit stays in the transport's
`sel`, so it is back after a custom effect publishes or the game returns
to Static mode. On the floor, `Vertical` behaves as `None` and `Both` as
`Horizontal`, and the README says so.

**Timing.** Call these after the build in the same frame. The tables then
describe the back buffer, which `commit()` puts on screen in the same
vblank that a game's OAM upload moves its sprites. Floor and sprites change
together.

Cost: 13 scanlines per visible object, 8 behind the camera, 4 culled (see
[Cycle budget](#cycle-budget)).

## plain_rotation.r65: `M7PlainRotation`, a plain at a true pitch

`M7Plain`'s pitch is a horizon shift: its ground perspective depends only
on the height, so tilting slides the picture, and it can't look straight
down. `M7PlainRotation` takes the camera's pitch as a real angle and
rebuilds its line tables for it, so the foreshortening changes as a real
camera's does. For a real camera 1/depth is linear in the screen line, so
a pitch or altitude change costs a few divisions and a table read per line.

`m7k_plain_rotation!(Name, STATE, Hdma, HDMA_STATE, rows)` is shaped like
`m7k_plain!`, with the default instance `M7PlainRotation` (state
`M7K_PLAIN_ROTATION`, 729 bytes) over `M7HDMA` and the row builder
`m7k_plain_rows_mul`. It implements `Mode7` and `Mode7Scan`, so a
per-line add-on written for the floor works with it: `examples/plain_rotation/`
puts the flyer's own sky over it. It includes only `core.r65`, which
holds the depth scale `M7K_ZRECIP` both per-line views read.

### The pitch, and its range

The camera's `pitch` is the angle θ in 256ths of a turn: 0 level, 64
straight down. `M7PlainRotation` takes **6..64** (8.4° to 90°) and clamps the
rest. The limit is the hardware's. The matrix pivots on the point under
the camera, at screen line 112 + 128·cot θ (`foot`), and Mode 7 clips its
(VOFS − Y0) term to 10-bit signed, so that point must be within 1023
lines. At θ = 6 it is 974; at 5 it would be 1150. Looking level or up
needs a different pivot, and is future work.

### Line tables

Rebuilt when the altitude or the pitch changes (`rebuild_lines`). With
the altitude H = height · 64 / scale_y texels (clamped to 40..248,
computed only when the height or scale_y changes), F = 128 pixels and v = line − 112, a line meets
the plane at lateral scale t = H / (F·sin θ + v·cos θ):

- **The interpolant.** zr(v) = (4096·sin θ + 32·v·cos θ) / H is linear
  in v. A few divisions a rebuild give zr at the center line (4096·sin θ
  overflows a u16, so it takes two), its step, the foot and the first
  ground line; then one `M7K_ZRECIP[zr >> 4]` read a line gives `line_z`
  (z = 64·t).
- **The far clip** is at zr = 4096 (z = 128, two texels a pixel). The
  first line nearer than it, `first`, is the horizon; the lines above it
  are sky.
- **`line_dist`** is ⌊z·(128·cos θ − v·sin θ) / 16384⌋, the forward ground
  distance each line shows from the point under the camera, at two 8×8
  products a line. It is signed: lines below `foot` show the ground behind
  that point. Biasing the middle factor by 2048 keeps it positive, and
  subtracting 2z after gives the floor exactly, with no sign to handle.
  The 8-bit z makes it jitter by up to a texel against a strict fall,
  which the projection search tolerates.

### Rows

Rebuilt on a heading change. The lateral terms are A = ±z·cos ψ and
C = ∓z·sin ψ; the forward ones are B = ±z·sin θ·sin ψ and
D = ±z·sin θ·cos ψ (ψ the heading). Each comes from a 1.7 factor and
`>> 5`, as the floor's. That makes 4 products a row, against the floor's
2, since A = D no longer holds. WRMPYA keeps z, so each product after the
first is one store, in the floor's quadrant-loop shape (four loops, no
sign masks). The keys are the floor's plus the table generation: heading,
generation, band top, row count and the transport's stamp; and for the
tables, horizon, ground lines, stamp and generation. An unchanged frame
costs 6 lines.

### Straight down

At θ = 64, cos θ = 0, so every line has the same matrix: A = D = z·cos ψ
and B = −C = z·sin ψ, a rotation scaled by the altitude, z = H/2, and stretched across by q:
at height 128 it is `M7Static`'s matrix for the same scales, but for z's
rounding and |cos| and |sin| halved. The build writes
**one row** and `segment` lays it out with the transport's `seg_hold`:
once entries pointing every line at that row. Turning costs 12 lines, about
`M7Static`'s. The row is in the back buffer, double-buffered like any
other. The transport's top matrix would have been simpler, but it is
shared by both buffers, so a turn would change the frame on screen
mid-picture.

`Mode7Scan::segment(p)` exists for this. A view appends its own region's
segments, so a game laying out several views (the split example) calls
`segment` instead of naming `seg_rows`, and a straight-down `M7PlainRotation` in a
half works too.

### Projection

`to_screen` is the floor's search over `M7PlainRotation`'s tables:
1. Rotate the offset into forward and lateral distances (`m7k_rotate14`).
2. Cull by the farthest |`line_dist`| plus that line's half width at the
   widest stretch, 4z.
3. Binary-search `line_dist` for sy, with signed compares.
4. sx = 128 ± r·size >> 8, with size `M7K_RECIP[z]`, times p when the
   scales differ (`m7k_mul_q8`).

`depth()` is the forward distance. `to_world` inverts it with
`line_dist`. A horizontal flip is kept and a vertical one dropped, as on
the floor.

### Measured

Bench cases 18–22 and 24, at height 72, in scanlines:

| Case | Lines |
|---|---|
| turning, pitch 16 (22.5°) | 184 |
| turning, pitch 16, stretched (56, 64) | 188 |
| turning, pitch 32 (45°) | 278 |
| turning, straight down | 12 |
| a pitch change at 16 (tables and rows) | 399 |
| unchanged | 7 |

- **Turning at 45° takes longer than a frame.** The 4-product row loop
  needs the tuning the floor's loop got.
- **The tables cost more than the demo's.** They take about 213 lines, of
  which `line_dist` is about half. The rest is stack-slot traffic in the
  loop.

**Accuracy.** Against an ideal ray-cast camera, the example's tests
require at least 85% of ground pixels within one texel at 8° and 16°, 90%
at 32° and 99% straight down. `to_screen` matches the view's own tables
exactly, and the ideal camera within 2 pixels across and 3 lines down.
The error is the 8-bit z (`M7K_ZRECIP` is `u8`) and the 1.7 forward
factor. The ground drawn has the same error, so sprites stay on it.

## Switching modes

A game with several views switches in vblank, straight after `wait_nmi!()`:

```rust
Old::stop();                              // when Old is an HDMA view
New::setup(&CAMERA, New::repeat(), New::flip());   // the same camera, so the view carries over
// and the NMI handler now calls New::nmi()
```

Nothing in the package records which view is in use: the game's NMI
handler calls the `nmi()` of the one it is using, and that call is the
choice. With nscene, it's each scene's NMI hook.

- **Into HDMA:** the transport's `setup` fills both buffers' tables before
  its channels go into the shadow, and the first `commit()` shows them at
  the top of a frame.
- **Out of HDMA:** `stop()` turns the channels off at once. M7A–D keep
  the last row's values until `M7Static::nmi` writes its matrix. A game
  with per-line bands of its own stops them too; BGMODE and TM keep the
  last values their tables wrote.
- **Mixing the types is not caught.** `M7Static::to_screen` in a floor
  frame answers for the Static matrix. Checking at run time would need a
  mode variable and a branch on every call. Each type has its own state,
  so it can't corrupt the other: the rule is to use the type whose `nmi()`
  the handler calls.

## HDMA channel map

| Ch | Default owner | Use |
|---|---|---|
| 0 | the game | free; stdlib's DMA uploads use it |
| 2, 3 | `M7HDMA` | M7A/B, M7C/D (indirect) |
| 1, 4–7 | the game | free (the flyer's sky bands use 4–6, the split's views 1 and 7) |

Any instance can take other channels. In Static mode HDMAEN belongs to
the game. With a transport set up, it writes HDMAEN every vblank from its
shadow, and the game adds its channels with `enable(mask)`.

## Cycle budget

Measured by `tests/bench/` on Mesen (HiROM, FastROM, HDMA running): the
V-counter latched before and after each piece, the NMIs between counted, in
scanlines of a 262-line frame. A frame has room for about 225 lines of
work at 60 fps. The bench's own overhead is 1 line. "+ sky" is the bench's
own copy of the flyer example's sky bands, built around the floor.

| Work | v0.1 | v0.2 |
|---|---|---|
| floor + sky, turning, pitch 0 (160 ground lines) | 213 | 144 |
| floor + sky, unchanged | 213 | 7 |
| floor alone, turning | 194 | 143 |
| floor + sky, turning, pitch −32 (192 lines) | 251 | 174 |
| floor + sky, turning, pitch 64 (96 lines) | 137 | 88 |
| the sky's tables, rewritten | 18 | 7 |
| line tables, on a height change | 191 | 159 |
| `to_screen`, visible / behind / culled | 15 / 8 / 15 | 13 / 8 / 4 |
| `to_screen` × 5 (the flyer's objects) | 66 | 56 |
| `M7Static::update` / `to_screen` | 10 / 16 | 10 / 16 |

Since v0.2 the bench reads 148 turning and 9 unchanged; the camera's
scales and height account for a third of a line of that (three byte
compares a frame). A stretched floor, scales (56, 64), takes the four-product
rows: 238 lines turning with the sky, past the frame's 225, so a stretched
flyer that turns runs at 30 fps.

- **Where v0.2 gains.** Build keys skip unchanged rows and tables; the
  quadrant loops drop the per-row sign masks; WRMPYA keeps z for the second
  product; the stores fill the multiplier's wait; the sky's bands write in
  place and COLDATA is indirect; `to_screen` culls before multiplying and
  does its products inline.
- **What it buys.** The flyer example, five objects projected, runs at 60
  fps while turning (30 in v0.1). A frame that changes the height also
  rebuilds the line tables, and drops to 30 fps.
- **What is left is code shape.** A row is about 170 CPU cycles, most of
  them stack-relative temporaries in slow WRAM around two 8-cycle
  multiplies. Further cuts would come from the compiler keeping the loop's
  index and constants in registers or the direct page; the bench is the
  way to see them.

## Code style

- **No `asm!()`** in mode7kit sources. If profiling shows an `asm!` is
  needed, it is measured first and justified in a comment beside it.
- **No global registers.** That means no `Y = pos; T[Y] = v`, no
  `X = angle & 0xFF; COS[X]`, and no `A = v; REG = A as u8; REG = B`. Use
  locals and indexing (`T[pos] = v`, `M7K_SIN[i as u16]`), and let the
  compiler choose registers. A write-twice register is written as
  `REG = v as u8; REG = (v >> 8) as u8;`.
- The hardware multiplier is driven through stdlib's `WRMPY` and `RDMPY`
  and mode7kit's `#[hw]` word `M7K_WRMPYB`, with `NOP(n)` for the wait, or
  the stores the wait can hold. DMA channels go through `M7K_DMA[n]`.
- Statics are named `M7K_*`, free functions `m7k_*`, instance macros
  `m7k_*!`. Public types are the `Mode7` trait, `M7Static`, `M7Coord`,
  `M7Camera`, `M7Repeat`, `M7Flip`, `M7KChannel` and the default
  instances `M7HDMA`, `M7Plain` and `M7PlainRotation`.
- A macro's locals are prefixed `m7k_`: R65 macros have no hygiene.
- Every public item has a `///` doc comment, and every file has a `//!`
  header naming what it includes and what it costs.

## Notes on dizworld

These are things the port fixes rather than copies:

- **The fade never ran.** `FADE_TABLE` and the COLDATA table are built, but
  `nmi_hdma_en = 0x0F` enables channels 0–3 only, and color math is never
  turned on. The flyer example's sky turns both on.
- **`pv_rebuild` is dead code** (it is never called), and it treats `$80|n`
  as "hold", which is backwards. The port follows the main loop, which gets
  the once and continuous meanings right.
- **ZTABLE** is 4096 entries, and the second half is unreachable.
- The per-frame NMI `MVN` copy of 128 bytes to $4300 is replaced by a
  one-time setup plus a per-frame write of A1Tn.

## Example ROMs and tests

`examples/` holds five ROMs, each shaped like `nscene/example`, with
`mode7kit = { path = "../.." }`, a README and Mesen-GDB pytest tests. All
but the beach ball use dizworld's assets (copied from
`r65docs/static/examples/assets/`, CC BY; each README carries the
attribution) and draw no sprites.

- **`examples/topdown/`** includes `static.r65`. The D-pad moves along and
  across the heading (its `CAMERA`'s `forward` / `strafe`), L/R turn, A/X
  zoom the camera in and out, both scales alike (`M7Static` reads the
  scales and ignores the height).
- **`examples/flyer/`** includes `plain.r65`, and has its own sky bands and
  `Horizon` background in `src/` (see its README). dizworld's controls;
  L/R change the camera's height, X/B its pitch, Start toggles
  `Horizontal`. It projects five world points with
  `M7Plain::to_screen` into `OBJECT_SCREEN` for the tests.
- **`examples/split/`** includes `plain.r65`: a second camera and floor
  instance, with its own bands, views and `m7k_split!` in `src/` (see its
  README). Pad 1's D-pad drives the top camera, Y/A/X/B the bottom one.
- **`examples/plain_rotation/`** includes `plain_rotation.r65`: the flyer with
  `M7PlainRotation` for the view, under the flyer's sky (its own copy in
  `src/`). X/B tilt from 8° to straight down. Its tests check the line
  tables and rows against the formulas, the held row straight down, the
  picture and the projection against a ray-cast camera.
- **`examples/beachball/`** includes `static.r65` for one object rather than
  a view: a beach ball, converted from a BMP by `r65x bmp2chr -m7` in the
  Makefile, spins and squashes over a sprite floor built from the r65docs
  platformer's tiles. Past the ball's edge is transparent, over a COLDATA
  sky gradient. Its design is in
  [its own DESIGN.md](examples/beachball/DESIGN.md).

`tests/` holds three test ROMs. Those that need a sky carry their own copy
of the flyer's bands and `Horizon` in `src/`.

- **`tests/switch/`**: one game with both modes, switching between
  `M7Plain` under `Horizon` and `M7Static` in vblank when a test writes
  `REQUEST`.
- **`tests/options/`**: non-default instances in three scenes: a 160-line
  transport on channels 1 and 3, with a floor under a `Horizon` with a HUD
  band and bands without COLDATA; a custom per-line effect on it; and `M7Static` on data
  uploaded by `mode7_upload_split!`, probing `to_world`.
- **`tests/bench/`**: the [cycle budget](#cycle-budget), with a budget per
  case about 10% over v0.2's numbers.

The tests check:

- every table's bytes, read by symbol, against the formulas above, and that
  the top-down build has none of the floor's tables or state;
- `M7Static`'s matrix and inverse for nine headings and camera scales,
  equal and stretched, and an exact quarter turn; that the height changes
  nothing; that it never stores to HDMAEN;
  the flat `to_world` for five headings and pixels;
- the top-down buttons: zoom, turn, the D-pad's sideways step;
- the camera's height and scale_y as the floor's height, clamped, and as
  the plain rotation's altitude, clamped to 40..248; stretched rows (the
  floor's four-product path, the plain rotation's lateral factors) and
  stretched `to_screen` in both views and the plain rotation's picture;
  straight down at height 128, the plain rotation's row is `M7Static`'s
  matrix for equal and unequal scales;
- the floor's line tables, indirect tables (entries, addresses,
  terminator), top unit and per-line A–D with their signs in all four
  quadrants and on the axes;
- that both buffers come into use and the shown one is always complete;
- the bands' BGMODE and TM tables and the indirect COLDATA entries and
  data;
- the floor projection against the line-distance search, hidden points
  included;
- the vertical flip: dropped on screen by the floor (by screenshot) but kept
  in the transport's `sel`;
- pitch: the split follows it and clamps at −32 and +64, the line tables
  are the same at every pitch, the pivot follows the foot, a projected
  point moves exactly `pitch` lines, and the X/B buttons;
- switching: a round trip restores each picture byte for byte and the
  channels with it; the Static view after the floor is the top-down ROM's
  own boot picture; the camera carries over both ways; the vertical flip
  survives the floor;
- options: a transport's size is 16·lines + 151 and the unused default
  transport and floor are gone; the channel numbers in HDMAEN; the HUD band's tables
  and its unchanging backdrop; the custom effect's rows and tables;
  `mode7_upload_split!` makes the top-down ROM's picture;
- the split screen: its channels; each half follows its own camera and
  leaves the other's pixels alone; the same camera in both halves gives
  the same sky exactly and the same floor but for rounding; the horizons,
  bands and views.

The restructure into instances kept the pictures: the top-down and switch
ROMs give v0.1's screenshots byte for byte. The flyer runs faster, so its
button-driven screenshots moved with the frame rate; a capture that writes
the camera, height and pitch and waits showed every view unchanged from
the restructure through the speed work, and the tests check the rows
themselves against the formulas.

## Limits and future work

- **Exact perspective.** A ≠ D lets the vertical foreshortening (D = λ·F/y)
  differ from the horizontal (A = λ). That costs 4 multiplies per line
  instead of 2. `M7Plain` keeps dizworld's A = D approximation;
  `M7PlainRotation` pays for A ≠ D.
- **Exact pitch below 8°.** The floor's [pitch](#pitch) is a y-shear;
  [`M7PlainRotation`](#plain_rotationr65-m7plainrotation-a-plain-at-a-true-pitch)
  is the exact view, from 8.4° to straight down. Level and upward views
  need a pivot other than the point under the camera.
- **`M7PlainRotation`'s cost.** Turning at 45° (275 lines) and a pitch change
  (395) take longer than a frame; its row and table loops need the work
  the floor's got. A 16-bit z would also lift its accuracy at shallow
  angles.
- **Per-band geometry.** A floor in a band shorter than the screen is the
  full screen's floor, cropped. A floor scaled to its band needs the
  `M7K_ROW_*` tables per band height, or a height parameter in them.
- **The row loop's code shape.** See [Cycle budget](#cycle-budget). A ROM
  product table (62 KB) was measured and dropped; it pays once the index
  stays in a register.
- **Height changes.** `rebuild_lines` costs 158 lines on the frame the
  floor's height changes. Spreading it over two frames, or
  keeping a few heights' tables, would keep 60 fps while climbing.
- **Projection.** 13 lines a visible object, of which the rotation is 5
  and the line search 2; the rest is calls and stack traffic.
- **Worlds larger than 1024 texels.** These need a 32-bit or 16.16 world
  coordinate and tilemap streaming into the 128×128 VRAM map. `M7Coord`
  would become the plane-local view of a larger world coordinate.
- **Object height above the floor** (a jumping or flying object). This is
  `to_screen` plus a vertical offset of height·`M7K_RECIP[z]` >> 8.

## Resolved during implementation

- `#[bank(auto)]` is a directive, not an item attribute, and auto-bank ROM
  statics must be `far static`. `M7K_ZRECIP` sits at the end of
  `core.r65` for that reason, after everything else in the file.
- `&$state.abi as u16` gives a field's 16-bit address for A1Tn. R65 has
  no bank-byte operator, so the `#[ram]` bank is the constant
  `M7K_RAM_BANK`, which R65's own tests pin.
- `near` and `far` are keywords (a local named `far` is a parse error
  inside a macro's expansion), and `const_assert!` is not allowed at the
  top level.
- A constant-false `if` is still type-checked, constant indices included:
  hence the examples' bands macro has a second arm with no COLDATA channel.
- Macros may write attributes on statics, `impl` blocks with associated
  consts, and array sizes from their arguments; `$T::f()` and `$T::CONST`
  resolve on the instance type (checked by scratch compiles before the
  restructure).

Compiler changes the package needed (R65 repository):

- v0.2: a `///` doc comment inside a macro body (on an item the macro
  writes) failed to parse after a nested `}`, where the lexer offered the
  next top-level item; doc comments in a macro body are now accepted and
  dropped. A `///` before a top-level macro invocation is accepted too.

- A multi-return may put a 2-byte value first from an m8 function (all of
  C, as a single `-> u16` is), which lets plain-parameter functions return
  `i16, i16` or `M7Coord, M7Coord`. B is then not free, so the order is
  A, X, Y.
- A loop counter promoted into X or Y moves (or falls back to the stack)
  when a call in its life returns a value in that register.
- `bool as u16` zero-extends; it was a plain move, keeping B's garbage.
- A short-lived value is not parked in X/Y while another value placed
  there is live.
- An interrupt handler loads the program's data bank (`$80`/`$00`), not
  PHK, which under HiROM was `$C0`, a bank with no low RAM.
- A trait method may return several values (`fn to_screen(..) -> i16, i16,
  u16;`): trait signatures resolved return types with the plain resolver
  and rejected the list. Found by a scratch ROM in the trait's shape before
  the redesign; the same ROM confirmed the rest worked as is (enum
  parameters, `Self::` defaults, dead-code removal of unused defaults, no
  type-id byte on a receiverless implementor).
