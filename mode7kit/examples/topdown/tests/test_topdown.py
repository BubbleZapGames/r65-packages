"""mode7kit's flat view, driven through the top-down example ROM.

Each test sets a view by writing the camera (its heading and its scales)
or pressing the example's buttons, lets the frame run, and checks the state that follows against the same formulas in Python:
the compile-time tables, `M7Static`'s matrix and the camera.
"""
import math

import pytest

from pathlib import Path

# Struct offsets (packed, declaration order).
S_SEL, S_A, S_B, S_C, S_D = 0, 1, 3, 5, 7          # M7Static
S_IA, S_IB, S_IC, S_ID = 9, 11, 13, 15
S_ZOOM = 27
CAM_HEADING, CAM_SX, CAM_SY, CAM_HEIGHT = 4, 5, 6, 7                       # M7Camera
ASM = Path(__file__).parent.parent / "build" / "main.asm"

def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def words(b, signed=True):
    w = [b[i] | b[i + 1] << 8 for i in range(0, len(b) - 1, 2)]
    return [s16(v) for v in w] if signed else w


def word(b, off):
    return s16(b[off] | b[off + 1] << 8)


# -- the tables, as the const fns build them ----------------------------------

def fsin(i):
    return round(math.sin(2 * math.pi * i / 256) * 256)


SINCOS = [fsin(i) for i in range(320)]
RECIP = [0x7FFF] + [16384 // z for z in range(1, 256)]


def q8(m, k):
    """m7k_smul_q8: sign-magnitude (m * k) >> 8, saturating."""
    mag = k if abs(m) >= 256 else (abs(m) * k) >> 8
    mag = min(mag, 0x7FFF)
    return -mag if m < 0 else mag


# -- driving the ROM ------------------------------------------------------------

def set_view(s, angle=None, scale=None, height=None):
    cam = s.resolve("CAMERA")
    if angle is not None:
        s.write(cam + CAM_HEADING, angle & 0xFF)
    if scale is not None:
        s.write(cam + CAM_SX, scale[0])
        s.write(cam + CAM_SY, scale[1])
    if height is not None:
        s.write(cam + CAM_HEIGHT, height)
    s.wait(3)


def state(s):
    return s.raw("M7K_STATIC").bytes()


def angle(s):
    return s.raw("CAMERA").bytes()[CAM_HEADING]


def camera(s):
    """CAMERA's x, y (10.6, unsigned)."""
    return words(s.raw("CAMERA").bytes()[:4], signed=False)


@pytest.fixture
def top(snes):
    snes.wait(30)
    return snes


# -- tables -----------------------------------------------------------------------

def test_lookup_tables(top):
    s = top
    assert words(s.raw("__M7K_SINCOS_data").bytes()) == SINCOS
    assert words(s.raw("__M7K_RECIP_data").bytes(), signed=False) == RECIP


def test_only_the_included_tables(top):
    """Features not used cost nothing: no depth or floor tables, no
    transport (a constant such as `M7K_ZRECIP_LAST` is only an equate)."""
    names = set(top.rom.symbols.names())
    for name in ("__M7K_ZRECIP_data", "__M7K_ROW_SKY_data", "M7K_HDMA", "M7K_PLAIN"):
        assert name not in names, name


# -- the flat view ----------------------------------------------------------------

@pytest.mark.parametrize("angle,zx,zy", [(0, 64, 64), (64, 64, 64), (32, 128, 128),
                                         (200, 40, 40), (100, 255, 255), (10, 16, 16),
                                         (0, 56, 64), (40, 64, 32), (150, 200, 90)])
def test_rotate_scale_matrix_and_inverse(top, angle, zx, zy):
    """The camera's heading turns the view and its scales zoom it, each on
    its screen axis."""
    s = top
    set_view(s, angle=angle, scale=(zx, zy))
    m = state(s)
    assert m[S_ZOOM] == zx
    sn, cs = SINCOS[angle], SINCOS[angle + 64]
    kx, ky = RECIP[zx], RECIP[zy]
    assert [word(m, o) for o in (S_A, S_B, S_C, S_D)] == \
        [q8(cs, kx), q8(sn, ky), -q8(sn, kx), q8(cs, ky)]
    assert [word(m, o) for o in (S_IA, S_IB, S_IC, S_ID)] == \
        [q8(cs, zx << 2), -q8(sn, zx << 2), q8(sn, zy << 2), q8(cs, zy << 2)]


def test_quarter_turn_is_exact(top):
    s = top
    set_view(s, angle=64, scale=(64, 64))
    m = state(s)
    assert [word(m, o) for o in (S_A, S_B, S_C, S_D)] == [0, 0x100, -0x100, 0]


def test_height_is_ignored(top):
    """A flat view has no height: writing it changes no matrix entry."""
    s = top
    set_view(s, angle=30, scale=(70, 60))
    before = state(s)
    set_view(s, height=20)
    assert state(s) == before


def test_static_never_writes_hdmaen():
    """Static mode leaves HDMAEN ($420C) to the game: none of `M7Static`'s
    functions store to it."""
    asm = ASM.read_text()
    bodies = [part.split("\n; ", 1)[0] for part in asm.split("\nM7Static__")[1:]]
    assert bodies and not any("$420C" in body for body in bodies)


def test_zoom_buttons(top):
    """A zooms the camera in and X out, both scales a step a frame, and the
    matrix follows."""
    s = top
    s.hold("a", frames=20).wait(2)
    cam = s.raw("CAMERA").bytes()
    assert 80 <= cam[CAM_SY] <= 86 and cam[CAM_SX] == cam[CAM_SY] == state(s)[S_ZOOM]
    s.hold("x", frames=40).wait(2)
    cam = s.raw("CAMERA").bytes()
    assert 40 <= cam[CAM_SY] <= 46 and cam[CAM_SX] == cam[CAM_SY] == state(s)[S_ZOOM]


def test_turn_buttons(top):
    """L turns one way and R the other, a step a frame."""
    s = top
    s.hold("l", frames=10).wait(2)
    turned = angle(s)
    assert 8 <= turned <= 12
    s.hold("r", frames=turned).wait(2)
    assert angle(s) == 0


@pytest.mark.parametrize("heading", [0, 40, 150])
def test_left_right_move_across_the_view(top, heading):
    """Right moves the camera along the heading turned a quarter clockwise,
    m7k_heading(angle - 64, 128), a step a frame; Left undoes it."""
    s = top
    set_view(s, angle=heading)
    a = (heading - 64) & 0xFF
    step = (q8(-SINCOS[a], 128), q8(-SINCOS[a + 64], 128))
    x0, y0 = camera(s)
    s.hold("right", frames=8).wait(3)
    x1, y1 = camera(s)
    dx, dy = s16((x1 - x0) & 0xFFFF), s16((y1 - y0) & 0xFFFF)
    big = max(step, key=abs)
    n = round((dx if big is step[0] else dy) / big)
    assert n >= 6 and (dx, dy) == (n * step[0], n * step[1])
    s.hold("left", frames=n).wait(3)
    assert camera(s) == [x0, y0]
