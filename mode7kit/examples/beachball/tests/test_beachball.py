"""The beach ball example: `M7Static` driving one object over a sprite floor.

The ball's matrix and the scroll are write-only on the PPU, so what reaches
the screen is checked by screenshot; `M7K_STATIC` and `BALL` by their state.
The motion tests run the ROM; the picture tests pause it (`BALL.paused`) and
write the ball's position, spin and zoom.
"""
import math
import struct
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).parent
ASSETS = HERE.parent / "assets"
TOP_ROW = 7                                     # screen line 0 in a screenshot
FLOOR = 176
REST = FLOOR - 32                               # the ball's centre resting on the floor
Q = 64                                          # Q10.6: positions and speeds in 1/64 pixel

# Struct offsets (packed, declaration order).
B_X, B_Y, B_VX, B_VY, B_ANGLE, B_ZX, B_ZY, B_SQUASH, B_PAUSED = 0, 2, 4, 6, 8, 10, 11, 12, 15
S_A, S_B, S_C, S_D = 1, 3, 5, 7                 # M7Static
S_CX, S_CY, S_HOFS, S_VOFS = 17, 19, 21, 23


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def word(b, off):
    return b[off] | b[off + 1] << 8


def rgb(c):
    """A BGR555 colour as Mesen draws it."""
    return tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31))


SKY = 0x6E61
SINCOS = [round(math.sin(2 * math.pi * i / 256) * 256) for i in range(320)]
RECIP = [0x7FFF] + [16384 // z for z in range(1, 256)]


def q8(m, k):
    """m7k_smul_q8: sign-magnitude (m * k) >> 8, saturating."""
    mag = k if abs(m) >= 256 else (abs(m) * k) >> 8
    mag = min(mag, 0x7FFF)
    return -mag if m < 0 else mag


def sky(line):
    """The backdrop on `line`: colour 0 plus the COLDATA step, saturating."""
    k = (line // 8) // 2
    return tuple(min(31, v + k) for v in (SKY & 31, (SKY >> 5) & 31, (SKY >> 10) & 31))


def sky_rgb(line):
    return tuple((v << 3) | (v >> 2) for v in sky(line))


# -- the floor, drawn from the platformer's tiles -------------------------------

def tile_pixels(chr_, tile):
    """An 8x8 4bpp tile's colour indices, rows top to bottom."""
    b = chr_[tile * 32:tile * 32 + 32]
    return [[((b[2 * y] >> (7 - x)) & 1) | ((b[2 * y + 1] >> (7 - x)) & 1) << 1
             | ((b[16 + 2 * y] >> (7 - x)) & 1) << 2 | ((b[17 + 2 * y] >> (7 - x)) & 1) << 3
             for x in range(8)] for y in range(8)]


def floor_block(chr_, tl, tr, bl, br):
    """A 16x16 block of colour indices from four 8x8 tiles."""
    t = [tile_pixels(chr_, n) for n in (tl, tr, bl, br)]
    return [t[0][y] + t[1][y] for y in range(8)] + [t[2][y] + t[3][y] for y in range(8)]


def expected_floor_line(line):
    """Line `line` of the floor as indices: the grass block, then dirt."""
    chr_ = (ASSETS / "platform.chr").read_bytes()
    row = line - FLOOR
    block = (floor_block(chr_, 0x0B, 0x25, 0x2A, 0x2B) if row < 16
             else floor_block(chr_, 0x22, 0x22, 0x22, 0x22))
    return block[row % 16] * 16


# -- driving the ROM -------------------------------------------------------------

def screen(s, tmp_path, name):
    img = Image.open(s.screenshot(tmp_path / f"{name}.png")).convert("RGB")
    return img.crop((0, TOP_ROW, 256, TOP_ROW + 224))


def put(s, x, y, angle=0, zx=64, zy=64):
    """Pauses the ball at pixel (x, y) with this spin and zoom."""
    base = s.resolve("BALL")
    s.write(base + B_PAUSED, 1)
    s.write(base + B_X, (x * Q) & 0xFFFF, 2)
    s.write(base + B_Y, (y * Q) & 0xFFFF, 2)
    s.write(base + B_ANGLE, angle << 8, 2)
    s.write(base + B_ZX, zx)
    s.write(base + B_ZY, zy)
    s.wait(4)


def ball_box(img):
    """The box around every pixel above the floor that isn't its line's sky."""
    xs, ys = [], []
    for y in range(FLOOR):
        want = sky_rgb(y)
        for x in range(256):
            if img.getpixel((x, y)) != want:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


@pytest.fixture
def ball(snes):
    snes.wait(30)
    return snes


# -- the picture -------------------------------------------------------------------

def test_sky_is_the_backdrop_plus_the_gradient(ball, tmp_path):
    """Away from the ball, every sky line is colour 0 plus its COLDATA step."""
    s = ball
    put(s, 200, 60)
    img = screen(s, tmp_path, "sky")
    for line in range(0, FLOOR, 8):
        assert img.getpixel((10, line)) == sky_rgb(line), line
    assert sky_rgb(0) != sky_rgb(FLOOR - 1)


@pytest.mark.parametrize("angle", [0, 32, 100])
def test_past_the_edge_is_transparent(ball, tmp_path, angle):
    """Inside the ball's 64x64 square but past its edge, the screen shows
    exactly the sky of its line; the cap at the centre is white."""
    s = ball
    put(s, 128, 90, angle=angle)
    img = screen(s, tmp_path, f"edge{angle}")
    assert img.getpixel((128, 90)) == (255, 255, 255)
    for dx, dy in ((26, 26), (-26, 26), (26, -26), (-26, -26), (0, 34), (34, 0)):
        x, y = 128 + dx, 90 + dy
        assert img.getpixel((x, y)) == sky_rgb(y), (dx, dy)


@pytest.mark.parametrize("x,y,zx,zy", [(128, 90, 64, 64), (60, 40, 64, 64),
                                       (180, 152, 76, 48)])
def test_ball_is_drawn_at_its_position(ball, tmp_path, x, y, zx, zy):
    """The disc's box is centred on the ball's pixel, 64 pixels across at
    zoom 64 and scaled per screen axis by the squash."""
    s = ball
    put(s, x, y, zx=zx, zy=zy)
    left, top, right, bottom = ball_box(screen(s, tmp_path, "pos"))
    w, h = 64 * zx // 64, 64 * zy // 64
    assert abs((left + right + 1) / 2 - x) <= 1 and abs((top + bottom + 1) / 2 - y) <= 1
    assert abs((right - left + 1) - w) <= 2 and abs((bottom - top + 1) - h) <= 2


@pytest.mark.parametrize("angle,zx,zy", [(0, 64, 64), (40, 76, 48), (200, 67, 60)])
def test_matrix_and_scroll(ball, angle, zx, zy):
    """rotate_scale's matrix, with the centre texel (32, 32) scrolled onto
    the ball's pixel."""
    s = ball
    put(s, 100, 70, angle=angle, zx=zx, zy=zy)
    m = s.raw("M7K_STATIC").bytes()
    sn, cs = SINCOS[angle], SINCOS[angle + 64]
    kx, ky = RECIP[zx], RECIP[zy]
    assert [s16(word(m, o)) for o in (S_A, S_B, S_C, S_D)] == \
        [q8(cs, kx), q8(sn, ky), -q8(sn, kx), q8(cs, ky)]
    assert [word(m, o) for o in (S_CX, S_CY, S_HOFS, S_VOFS)] == \
        [32, 32, (32 - 100) & 0xFFFF, (32 - 70) & 0xFFFF]


def test_floor_is_the_platformer_tiles(ball, tmp_path):
    """Lines 176-223 are the grass block over two rows of dirt, 16 pixels
    repeating, in the platformer's palette; a transparent pixel shows the
    sky of its line."""
    s = ball
    img = screen(s, tmp_path, "floor")
    pal = struct.unpack("<16H", (ASSETS / "platform.pal").read_bytes())
    for line in range(FLOOR, 224):
        want = [sky_rgb(line) if i == 0 else rgb(pal[i]) for i in expected_floor_line(line)]
        got = [img.getpixel((x, line)) for x in range(256)]
        assert got == want, line


# -- the motion ---------------------------------------------------------------------

def test_floor_never_changes_while_the_ball_moves(ball, tmp_path):
    """The ball never draws on the floor's lines, gaps in the grass included."""
    s = ball
    floors = []
    for i in range(6):
        floors.append(screen(s, tmp_path, f"m{i}").crop((0, FLOOR, 256, 224)).tobytes())
        s.wait(7)
    assert len(set(floors)) == 1


def test_it_bounces_squashes_and_never_settles(ball):
    """Over 10 seconds the ball keeps landing, squashing (bottom on the
    floor, wider than tall) and leaving the floor again."""
    s = ball
    base = s.resolve("BALL")
    landings, squashed, top = 0, set(), 999
    for frame in range(600):
        s.wait(1)
        b = s.raw("BALL").bytes()
        y = s16(word(b, B_Y)) // Q
        if b[B_SQUASH]:
            zx, zy = b[B_ZX], b[B_ZY]
            assert zx > 64 > zy and y == FLOOR - zy // 2
            squashed.add(zy)
            if b[B_SQUASH] == 6:
                landings += 1
        if frame >= 480:
            top = min(top, y)
    assert landings >= 5 and min(squashed) == 48
    assert top < FLOOR - 32 - 30                  # still bouncing well clear at the end


def test_it_rolls_the_way_it_moves(ball):
    """The spin follows the horizontal speed: 1.25 steps a pixel, so 5/256
    of a step per 1/64 pixel."""
    s = ball
    b0 = s.raw("BALL").bytes()
    s.wait(1)
    b1 = s.raw("BALL").bytes()
    vx = s16(word(b1, B_VX))
    turned = (word(b1, B_ANGLE) - word(b0, B_ANGLE)) & 0xFFFF
    assert vx and s16(turned) == 5 * vx


def test_buttons(ball):
    """A kicks the ball up, right pushes it faster, Start pauses it."""
    s = ball
    base = s.resolve("BALL")
    s.write(base + B_SQUASH, 0)
    s.a()                                          # the tap takes 6 frames: 6 of gravity
    assert s16(word(s.raw("BALL").bytes(), B_VY)) <= -6 * Q + 6 * 12
    s.write(base + B_VX, Q // 2, 2)
    s.hold("right", frames=4)
    assert s16(word(s.raw("BALL").bytes(), B_VX)) > Q // 2
    s.start()
    before = s.raw("BALL").bytes()
    s.wait(10)
    assert s.raw("BALL").bytes()[B_PAUSED] == 1 and s.raw("BALL").bytes() == before


def test_a_kick_above_the_top_comes_back_down(ball):
    """Kicked near the top, the ball rises past line 0 (its y goes negative,
    with no wrap) and falls back to land on the floor, from a frame that
    was within one frame's fall of it."""
    s = ball
    base = s.resolve("BALL")
    put(s, 100, 3)
    s.write(base + B_VY, 0, 2)
    s.write(base + B_SQUASH, 0)
    s.write(base + B_PAUSED, 0)
    s.a()
    top, prev = 999, None
    for _ in range(180):
        s.wait(1)
        b = s.raw("BALL").bytes()
        y, vy = s16(word(b, B_Y)), s16(word(b, B_VY))
        if b[B_SQUASH]:
            break
        top = min(top, y)
        prev = (y, vy)
    else:
        pytest.fail("never landed")
    assert top < -32 * Q                           # well above the screen
    py, pvy = prev
    assert pvy > 0 and py + pvy + 12 >= REST * Q   # it fell onto the floor
