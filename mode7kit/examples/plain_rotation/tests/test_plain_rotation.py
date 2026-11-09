"""mode7kit's true-pitch plain, M7PlainRotation, driven through the plain
rotation example ROM.

Each test sets a view by writing the camera (heading, scales, height,
pitch), lets
the frame run, and checks the view's state against the same integer math
in Python, and its picture and projection against an ideal ray-cast camera.
"""
import math
import struct
from pathlib import Path

import pytest
from PIL import Image

HERE = Path(__file__).parent
ASSETS = HERE.parent.parent / "flyer" / "assets"

# Struct offsets (packed, declaration order).
H_SEL, H_CX, H_CY, H_HOFS, H_VOFS, H_BACK = 0, 1, 3, 5, 7, 9          # M7HDMA
H_ABI, H_CDI, H_AB, H_CD = 21, 85, 149, 1941
P_SKY, P_GROUND, P_BUILT_SY, P_BUILT_PITCH, P_FIRST = 1, 2, 3, 4, 6      # M7PlainRotation
P_FOOT, P_SIN_T, P_DOWN, P_CY, P_VOFS = 7, 9, 11, 20, 24
P_LINE_Z, P_LINE_DIST = 26, 250
CAM_HEADING, CAM_SX, CAM_SY, CAM_HEIGHT, CAM_PITCH = 4, 5, 6, 7, 8         # M7Camera
DATA_WORDS = 448
IND = 32
CLIP = 4096
HIDDEN = 0x7FFF
HEIGHT = 72                      # the example's, texels up
OBJECT_X = [512, 560, 470, 600, 512]
OBJECT_Y = [400, 450, 470, 300, 540]


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def words(b, signed=True):
    w = [b[i] | b[i + 1] << 8 for i in range(0, len(b) - 1, 2)]
    return [s16(v) for v in w] if signed else w


def word(b, off, signed=True):
    v = b[off] | b[off + 1] << 8
    return s16(v) if signed else v


SINCOS = [round(math.sin(2 * math.pi * i / 256) * 256) for i in range(320)]
ZRECIP = [255] + [min(255, 32768 // i) for i in range(1, 2321)]


def mul_q8(m, k):
    if m >= 256:
        return min(k, 0x7FFF)
    return min(((m * (k & 0xFF)) >> 8) + m * (k >> 8), 0x7FFF)


def alt(height, sy=64):
    """The altitude, texels: height · 64 / scale_y, clamped to 40..248."""
    return min(max((height << 6) // max(sy, 1), 40), 248)


def lateral(sx, sy):
    """m7k_lateral: (texels per pixel across, pixels per texel), 8.8."""
    y = max(sy, 1)
    x = min(max(sx, (y >> 1) + 1), min(y << 1, 255))
    if x == y:
        return 0x100, 0x100
    return (y << 8) // x, (x << 8) // y


def stretch(v, q):
    return min((v * q) >> 8, 0x7FFF)


def q8(m, k):
    """m7k_smul_q8: sign-magnitude (m * k) >> 8, saturating: `M7Static`'s."""
    mag = k if abs(m) >= 256 else (abs(m) * k) >> 8
    mag = min(mag, 0x7FFF)
    return -mag if m < 0 else mag


STRETCHED = [(64, 64), (56, 64), (80, 64), (64, 40)]


def tables(theta, height, sy=64):
    """rebuild_lines, step for step: (first, foot, line_z, line_dist)."""
    hh = alt(height, sy)
    s, c = SINCOS[theta], SINCOS[theta + 64]
    zr_c = (((s << 6) // hh) << 6) + (((s << 6) % hh) << 6) // hh
    step = ((c << 5) + (hh >> 1)) // hh
    foot = 112 if s >= 256 else 112 + (c << 7) // s
    zs, y = zr_c - 112 * step, 0
    if zs < CLIP:
        if step == 0:
            y = 224
        else:
            y = min((CLIP - zs + step - 1) // step, 224)
            zs += y * step
    vs, zr = (y - 112) * s, zs & 0xFFFF
    zs_, ds = [], []
    for _ in range(224 - y):
        z = ZRECIP[min(zr >> 4, 2320)]
        wb = (c << 3) - (vs >> 4) + 2048
        d = ((((z * (wb & 0xFF)) >> 8) + z * (wb >> 8)) >> 2) - 2 * z
        assert d == (z * (wb - 2048)) // 1024
        zs_.append(z)
        ds.append(d)
        zr = (zr + step) & 0xFFFF
        vs += s
    return y, foot, zs_, ds


def row(z, angle, sin_t, q=0x100):
    """One row's A, B, C, D, stretched across by q."""
    cos, sin = SINCOS[angle + 64], SINCOS[angle]
    ac, as_ = abs(cos), abs(sin)
    lc, ls = ac >> 1, as_ >> 1
    if q != 0x100:
        lc, ls = stretch(lc, q), stretch(ls, q)
    fc, fs = mul_q8(sin_t, ac) >> 1, mul_q8(sin_t, as_) >> 1
    la, lb = (z * lc) >> 5, (z * ls) >> 5
    fa, fb = (z * fc) >> 5, (z * fs) >> 5
    a, d = (-la, -fa) if cos < 0 else (la, fa)
    b, c = (-fb, lb) if sin < 0 else (fb, -lb)
    return a, b, c, d


# -- the ideal camera ----------------------------------------------------------------

MD7 = (ASSETS / "bg.md7").read_bytes()
MAP, CHR = MD7[0::2], MD7[1::2]
PAL = struct.unpack("<%dH" % (len((ASSETS / "bg.pal").read_bytes()) // 2),
                    (ASSETS / "bg.pal").read_bytes())
BACKDROP = 0x76F1


def rgb(c):
    return tuple((v << 3) | (v >> 2) for v in (c & 31, (c >> 5) & 31, (c >> 10) & 31))


def texel(tx, ty):
    tx, ty = int(math.floor(tx)) & 1023, int(math.floor(ty)) & 1023
    i = CHR[MAP[(ty >> 3) * 128 + (tx >> 3)] * 64 + (ty & 7) * 8 + (tx & 7)]
    return rgb(BACKDROP) if i == 0 else rgb(PAL[i])


def ray(theta, height, heading, x, y, cam=(512, 512), scale=(64, 64)):
    """The world point an ideal camera shows at pixel (x, y)."""
    s, c = SINCOS[theta] / 256, SINCOS[theta + 64] / 256
    sh, ch = SINCOS[heading] / 256, SINCOS[heading + 64] / 256
    h = alt(height, scale[1])
    v = y - 112
    lam = h / (128 * s + v * c)
    fwd, lat = lam * (128 * c - v * s), lam * (x - 128) * scale[1] / scale[0]
    return cam[0] - fwd * sh + lat * ch, cam[1] - fwd * ch - lat * sh


def project(theta, height, heading, wx, wy, cam=(512, 512), scale=(64, 64)):
    """Where an ideal camera shows world point (wx, wy): (sx, sy)."""
    s, c = SINCOS[theta] / 256, SINCOS[theta + 64] / 256
    sh, ch = SINCOS[heading] / 256, SINCOS[heading + 64] / 256
    h = alt(height, scale[1])
    dx, dy = wx - cam[0], wy - cam[1]
    fwd, lat = -dx * sh - dy * ch, dx * ch - dy * sh
    depth = fwd * c + h * s
    across = 128 * lat / depth * scale[0] / scale[1]
    return 128 + across, 112 + 128 * (h * c - fwd * s) / depth


def match(got, theta, height, heading, top, scale=(64, 64)):
    """The share of ground pixels within one pixel of the ideal camera."""
    near = 0
    for y in range(top, 224):
        for x in range(256):
            p = got.getpixel((x, y))
            wx, wy = ray(theta, height, heading, x, y, scale=scale)
            if any(texel(wx + ox, wy + oy) == p for ox in (-1, 0, 1) for oy in (-1, 0, 1)):
                near += 1
    return near / ((224 - top) * 256)


# -- driving the ROM --------------------------------------------------------------

def set_view(s, angle=None, height=None, pitch=None, scale=(64, 64)):
    cam = s.resolve("CAMERA")
    if angle is not None:
        s.write(cam + CAM_HEADING, angle & 0xFF)
    if height is not None:
        s.write(cam + CAM_HEIGHT, height)
    if scale is not None:
        s.write(cam + CAM_SX, scale[0])
        s.write(cam + CAM_SY, scale[1])
    if pitch is not None:
        s.write(cam + CAM_PITCH, pitch & 0xFF)
    s.wait(8)


def plain(s):
    return s.raw("M7K_PLAIN_ROTATION").bytes()


def hdma(s):
    return s.raw("M7K_HDMA").bytes()


def shown(s, field):
    h = hdma(s)
    k = h[H_BACK] ^ 1
    return list(h[field + IND * k:field + IND * (k + 1)]), k


def rows(s, field, k):
    return words(hdma(s)[field + 2 * DATA_WORDS * k:field + 2 * DATA_WORDS * (k + 1)])


def object_screen(s):
    return words(s.raw("OBJECT_SCREEN").bytes())


@pytest.fixture
def pl(snes):
    snes.wait(30)
    return snes


# -- tables ---------------------------------------------------------------------

@pytest.mark.parametrize("theta,height,sy", [(6, HEIGHT, 64), (16, HEIGHT, 64), (32, 50, 64),
                                             (48, 90, 64), (64, HEIGHT, 64), (24, 128, 64),
                                             (40, 248, 64), (16, 20, 64), (64, 255, 64),
                                             (16, 72, 128), (32, 100, 50), (24, 200, 32)])
def test_line_tables(pl, theta, height, sy):
    """The first ground line, the foot and both line tables, as the formulas,
    at the altitude height · 64 / scale_y (clamped to 40..248 texels)."""
    s = pl
    set_view(s, angle=0, height=height, pitch=theta, scale=(sy, sy))
    p = plain(s)
    first, foot, z, d = tables(theta, height, sy)
    assert (p[P_BUILT_SY], p[P_BUILT_PITCH], p[P_FIRST]) == (sy, theta, first)
    assert (p[P_SKY], p[P_GROUND]) == (first, 224 - first)
    assert word(p, P_FOOT, signed=False) == foot
    assert p[P_DOWN] == (theta == 64)
    n = len(z)
    assert list(p[P_LINE_Z:P_LINE_Z + n]) == z
    assert words(p[P_LINE_DIST:P_LINE_DIST + 2 * n]) == d
    # it falls from the horizon down, but for a texel of z's 8-bit rounding
    assert all(d[i + 1] <= d[i] + 1 for i in range(n - 1))


@pytest.mark.parametrize("pitch,used", [(0, 6), (-32, 6), (5, 6), (64, 64), (100, 64)])
def test_pitch_is_clamped(pl, pitch, used):
    """The camera's pitch is the view's angle, clamped to 6..64."""
    s = pl
    set_view(s, angle=0, height=HEIGHT, pitch=pitch)
    assert plain(s)[P_BUILT_PITCH] == used


@pytest.mark.parametrize("scale", STRETCHED)
@pytest.mark.parametrize("angle", [10, 70, 150, 200, 0, 64, 128, 192])
def test_rows(pl, angle, scale):
    """Four products a row, with each quadrant's signs, the lateral ones
    stretched by scale_y / scale_x."""
    s = pl
    set_view(s, angle=angle, height=HEIGHT, pitch=20, scale=scale)
    p = plain(s)
    first, _, z, _ = tables(20, HEIGHT, scale[1])
    q, _ = lateral(*scale)
    sin_t = word(p, P_SIN_T, signed=False)
    t, k = shown(s, H_ABI)
    ab, cd = rows(s, H_AB, k), rows(s, H_CD, k)
    for l, zz in enumerate(z):
        a, b, c, d = row(zz, angle, sin_t, q)
        assert (ab[2 * l], ab[2 * l + 1], cd[2 * l], cd[2 * l + 1]) == (a, b, c, d), l


def test_pivot_is_the_point_under_the_camera(pl):
    s = pl
    set_view(s, angle=0, height=HEIGHT, pitch=24)
    p = plain(s)
    _, foot, _, _ = tables(24, HEIGHT)
    assert word(p, P_VOFS, signed=False) == (word(p, P_CY, signed=False) - foot) & 0xFFFF


# -- straight down -----------------------------------------------------------------

@pytest.mark.parametrize("angle", [0, 40, 100])
def test_straight_down_is_one_held_row(pl, angle):
    """At pitch 64 every line shares one matrix: one row, held for 224
    lines by once entries, pivoting on the screen's center."""
    s = pl
    set_view(s, angle=angle, height=HEIGHT, pitch=64)
    p = plain(s)
    assert p[P_DOWN] == 1 and (p[P_SKY], p[P_GROUND]) == (0, 224)
    t, k = shown(s, H_ABI)
    entries = []
    i = 0
    while t[i]:
        entries.append((t[i], t[i + 1] | t[i + 2] << 8))
        i += 3
    assert [e[0] for e in entries] == [127, 224 - 127], "once entries, no continuous"
    assert entries[0][1] == entries[1][1], "both hold the same row"
    z = tables(64, HEIGHT)[2][0]
    ab, cd = rows(s, H_AB, k), rows(s, H_CD, k)
    a, b, c, d = row(z, angle, 256)
    assert (ab[0], ab[1], cd[0], cd[1]) == (a, b, c, d)
    assert a == d and b == -c
    h = hdma(s)
    assert word(h, H_VOFS, signed=False) == (word(h, H_CY, signed=False) - 112) & 0xFFFF
    assert word(h, H_HOFS, signed=False) == (word(h, H_CX, signed=False) - 128) & 0xFFFF


@pytest.mark.parametrize("scale", [(64, 64), (56, 64), (80, 48), (100, 100)])
@pytest.mark.parametrize("angle", [0, 40, 100])
def test_straight_down_at_height_128_is_static_modes_picture(pl, angle, scale):
    """Straight down at height 128 the held row is `M7Static`'s matrix for
    the same scales, but for the rounding of the altitude, of z (a byte:
    about 40 at scale 100, so 2.5% of its value), of the stretch and of the
    halved |cos| and |sin|: within 3%, or 2."""
    s = pl
    set_view(s, angle=angle, height=128, pitch=64, scale=scale)
    t, k = shown(s, H_ABI)
    ab, cd = rows(s, H_AB, k), rows(s, H_CD, k)
    sn, cs = SINCOS[angle], SINCOS[angle + 64]
    kx, ky = 16384 // scale[0], 16384 // scale[1]
    static = (q8(cs, kx), q8(sn, ky), -q8(sn, kx), q8(cs, ky))
    held = (ab[0], ab[1], cd[0], cd[1])
    assert all(abs(g - w) <= max(2, abs(w) * 3 // 100) for g, w in zip(held, static)), (held, static)


# -- against an ideal camera ---------------------------------------------------------

@pytest.mark.parametrize("theta,least,scale", [(8, 0.85, (64, 64)), (16, 0.85, (64, 64)),
                                               (32, 0.9, (64, 64)), (64, 0.99, (64, 64)),
                                               (32, 0.9, (56, 64)), (64, 0.99, (80, 48))])
def test_picture_matches_a_ray_cast(pl, tmp_path, theta, least, scale):
    """The ground, below the haze, matches an ideal pitched camera, stretched
    by the scales, to within one texel on most pixels: the error is the
    8-bit z."""
    s = pl
    set_view(s, angle=10, height=HEIGHT, pitch=theta, scale=scale)
    top = plain(s)[P_SKY]
    if theta < 64:
        top += 16                      # under the haze's 16 lines
    got = Image.open(s.screenshot(tmp_path / f"p{theta}.png")).convert("RGB").crop((0, 7, 256, 231))
    assert match(got, theta, HEIGHT, 10, top, scale) >= least


@pytest.mark.parametrize("scale", STRETCHED)
@pytest.mark.parametrize("theta", [12, 24, 40, 64])
def test_to_screen_follows_the_tables(pl, theta, scale):
    """Heading 0, so an object's offset is its forward distance and its
    lateral one exactly: sy is the first line whose distance is not past
    it, sx its lateral offset at that line's scale, stretched."""
    s = pl
    set_view(s, angle=0, height=HEIGHT, pitch=theta, scale=scale)
    first, _, z, d = tables(theta, HEIGHT, scale[1])
    _, px = lateral(*scale)
    pos = object_screen(s)
    for i in range(5):
        f, r = 512 - OBJECT_Y[i], OBJECT_X[i] - 512
        if not (d[-1] <= f <= d[0]):
            assert pos[2 * i + 1] == HIDDEN, i
            continue
        lo, hi = 0, len(d) - 1
        while lo < hi:
            mid = (lo + hi) >> 1
            lo, hi = (mid + 1, hi) if d[mid] > f else (lo, mid)
        size = 16384 // z[lo]
        if px != 0x100:
            size = stretch(size, px)
        off = (abs(r) * size) >> 8
        sx = 128 + (-off if r < 0 else off)
        assert (pos[2 * i], pos[2 * i + 1]) == (sx, first + lo), i


@pytest.mark.parametrize("scale", STRETCHED)
@pytest.mark.parametrize("theta", [12, 24, 40])
def test_to_screen_matches_a_ray_cast(pl, theta, scale):
    """Every object the view shows is within 2 pixels across and 3 lines
    down of where an ideal camera puts it, the 8-bit z's error the ground
    it stands on has too; the ones it hides are off the ground it draws."""
    s = pl
    set_view(s, angle=0, height=HEIGHT, pitch=theta, scale=scale)
    pos = object_screen(s)
    shown_any = False
    for i in range(5):
        sx, sy = pos[2 * i], pos[2 * i + 1]
        ix, iy = project(theta, HEIGHT, 0, OBJECT_X[i], OBJECT_Y[i], scale=scale)
        if sy == HIDDEN:
            assert not (plain(s)[P_SKY] <= iy < 224 and 0 <= ix < 256), i
            continue
        shown_any = True
        assert abs(sx - ix) <= 2 and abs(sy - iy) <= 3, (i, sx, sy, ix, iy)
    assert shown_any


def test_only_the_plain_rotation(pl):
    """The floor's file, which the view's no longer includes, costs nothing:
    no floor state, no floor tables."""
    names = set(pl.rom.symbols.names())
    assert "M7K_PLAIN" not in names and "M7K_PLAIN_ROTATION" in names
    assert "__M7K_ROW_SKY_data" not in names
