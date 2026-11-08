# beachball: design

A beach ball spins and bounces across a grass floor. It shows
`M7Static` driving one object, not a world view: the ball is the whole Mode 7
layer, rotated for the spin and scaled on the screen axes for the squash. The
floor is sprites built from the r65docs platformer's tiles
(`assets/platform.chr` and `platform.pal`).

## Screen

The whole screen is Mode 7, with BG1 and sprites on (TM = BG1 | OBJ).

**The ball is BG1** and occupies lines 0–175.

**The floor is sprites, in front of BG1.** It fills lines 176–223:
- 16×16 sprites (OBJSEL size 3, so the small size is 16×16 and the OAM high
  table stays zero);
- 16 columns by 3 rows, which is 48 sprites;
- the top row is the platformer's grass block and the two rows under it are
  dirt.

No HDMA mode split is needed. A Mode 7 line shows sprites, so the floor and
the ball share the screen. Sixteen 16×16 sprites on one line are 32 sprite
tiles, inside the PPU's 34-tile limit per line.

**The sprite tiles.** The grass block is the platformer's 8×8 tiles `$0B` and
`$25` over `$2A` and `$2B`, row 22 over row 23 of `platform.tilemap`. Dirt is
`$22` four times. A 16×16 sprite reads tiles n, n+1, n+16 and n+17, so setup
copies those 8×8 tiles out of `platform.chr` into that layout, 32 bytes each:
- the grass block at OBJ tiles 0, 1, 16 and 17;
- the dirt block at 2, 3, 18 and 19.

**The OAM image is a constant ROM table** built by a `const fn`: 48 floor
entries, the other 80 sprites off screen at y = 240, and a zero high table.
It is DMA'd once in force blank, since nothing on the floor moves.

**VRAM.** The Mode 7 data fills words `$0000–$3FFF`. The OBJ tiles start at
`$6000` (OBJSEL base 3).

**CGRAM.** Each kind of art keeps its own range:

| Colours | What |
|---|---|
| 0 | The backdrop: the sky (`ball.bmp`'s transparent index) |
| 1–9 | The ball (Mode 7 8bpp) |
| 128–143 | The floor's 4bpp colours, `platform.pal` loaded as OBJ palette 0 |

A floor pixel of colour 0 is transparent, so the sky shows through gaps in the
grass.

**The sky** is the platformer's colour 0 (`$6E61`), which `ball.bmp` also
stores at its transparent index 0. It is brightened towards the
floor by colour math on the backdrop alone: CGWSEL = 0 (fixed colour addend),
CGADSUB = `$20` (add, backdrop). One HDMA channel writes COLDATA every 8
lines, from a table in low RAM. Because the sky isn't flat, it proves the
square around the disc is see-through, not painted sky colour.

## The ball

The ball is `assets/ball.bmp`, a 64×64 8-bit indexed bitmap: index 0 is
transparent, and 1–9 are the ball's colours. The Makefile converts it with
`r65x bmp2chr assets/ball.bmp -o build/ball.chr -m7 -p -f`:
- **`-m7`** writes Mode 7 tiles, one byte a pixel: 64 tiles in reading order,
  8 a row.
- **`-p`** writes `build/ball.pal`, the bitmap's 10 colours.
- **`-f`** writes the whole bitmap. Without it, bmp2chr truncates its output
  to the size of a `ball.chr` already there.

bmp2chr writes no Mode 7 map, so the ROM builds one with a `const fn`. It is
128×128 with the ball's tiles in its top-left 8×8 corner, putting the ball's
centre on texel (32, 32), and tile 0 everywhere else. Tile 0 is the bitmap's
own top-left block, which lies past the disc's edge, so it is blank.
`upload_ball` DMAs the map to the low VRAM bytes and the 4 KB of tiles to the
high ones.

The drawing:
- six panels around a white cap: red, white, yellow, white, blue, white;
- each panel a shade darker near the rim, and a dark outline. Both are
  symmetric about the centre, so they look right at every angle.

**Transparent means the area past the ball's edge.** Inside the 64×64 square
the corners outside the disc are colour 0. Outside the square the map is tile
0. M7SEL is `M7Repeat::Transparent`, so nothing outside the 1024×1024 map
draws either. Only the disc ever covers the sky.

## Motion

Positions and speeds are `Q10` (stdlib Q10.6: signed, 1/64 pixel, −512 to
+511), the same scale as mode7kit's `M7Coord`. Signed matters: a ball kicked
near the top rises past line 0 to a negative y and falls back, where an
unsigned position would wrap to the bottom and land at once. Every motion
constant is a whole number of 1/64ths: gravity 0.1875, kick −6, push 0.0625,
minimum bounce 4, top speed 3. The angle stays a `u16`, 8.8 of a 256-step
turn, and the zoom mode7kit's `u8` (64 = 1.0).

Each frame:
- **Gravity** acts on the vertical speed. The ball bounces with a restitution
  of about 7/8 and is kicked back up to a minimum height once a bounce gets
  too small, so it never settles.
- **Horizontal speed** reverses at the screen edges.
- **Spin.** The angle advances by the horizontal speed over the radius, so the
  ball rolls rather than slides, and reverses with it.
- **Squash.** While it touches the floor the ball squashes for 6 frames:
  vertical zoom down to about 75%, horizontal up to about 120%. Its bottom
  stays on line 176, the floor's top.
- **The matrix.** `M7Static::rotate_scale(angle, zx, zy)` puts the zoom on
  the screen axes, so the squash stays vertical while the ball spins. Then
  `set_center(32, 32, 32 − x, 32 − y)` puts the centre texel at the ball's
  pixel, and `M7Static::nmi()` writes it all in vblank.

**Controls**, for poking at it: A kicks the ball up, the D-pad pushes it left
and right, and Start pauses.

## Tests

- TM and OBJSEL, and the sky's HDMA channel in HDMAEN.
- The OAM image: 48 floor sprites in a 16 × 3 grid from line 176, with the
  rest off screen.
- The floor:
  - lines 176–223 are the same in every frame while the ball moves;
  - its grass and dirt pixels match the platformer's tiles under palette 0.
- The ball never draws below line 176.
- With the motion paused at set values written to RAM:
  - the matrix for three angle and squash pairs;
  - the ball's centre pixel on screen matches its position;
  - the corners of the ball's square, past its edge, show exactly the sky of
    their line, and the disc doesn't.
- Kicked from line 3, the ball rises above the top of the screen (a negative
  y) and lands on the floor from a frame within one fall of it, rather than
  wrapping and landing at the top of its rise.
