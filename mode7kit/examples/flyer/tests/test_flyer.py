"""mode7kit's perspective floor and horizon, driven through the flyer
example ROM.

Each test sets a view by writing mode7kit's state (the camera's heading,
`M7Floor`'s height and pitch) or pressing the example's buttons, lets the
frame run, and checks the state that follows against the same formulas in
Python: the compile-time tables, the HDMA tables the floor and the horizon
split are built in, and the floor projection.
"""
import math

import pytest

# Struct offsets (packed, declaration order).
H_SEL, H_CY, H_VOFS, H_BACK, H_READY, H_HDMAEN = 0, 3, 7, 9, 10, 11   # M7HDMA
H_TOP, H_ABI, H_CDI, H_AB, H_CD = 13, 21, 85, 149, 1941
F_HEIGHT, F_PITCH, F_SKY, F_GROUND, F_FOOT = 0, 1, 3, 4, 5            # M7Floor
F_CY, F_VOFS, F_LINE_Z, F_LINE_DIST = 16, 20, 22, 470
B_BGM, B_TMT, B_COL, B_FADE, B_STRIDE, B_COL_STRIDE = 11, 37, 63, 107, 13, 22  # M7Bands
CAM_ANGLE = 4                                                          # M7Camera
PITCH_DOWN, PITCH_UP = 32, 64
DATA_WORDS = 448                 # one buffer of rows: 224 lines x A, B (or C, D)
IND = 32                         # one buffer of an indirect table

OBJECT_X = [512, 560, 470, 600, 8]
OBJECT_Y = [400, 450, 470, 300, 512]
HIDDEN = 0x7FFF


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
ZRECIP = [255] + [min(255, 32768 // i) for i in range(1, 2321)]


def sky_of(h):
    return 32 + (h >> 1)


def zr0(h):
    return (1 << 21) // (384 + 2 * h)


def zr_step(h):
    zr1 = max((1 << 21) // (64 + (h >> 1)), zr0(h))
    return (zr1 - zr0(h)) // (224 - sky_of(h))


def foot_of(h):
    """Lines from the horizon to the point under the camera."""
    return 224 - sky_of(h) + PITCH_DOWN


def line_z(h):
    """z per line from the horizon down to the foot, whatever the pitch."""
    z, zr = [], zr0(h)
    for _ in range(foot_of(h)):
        z.append(ZRECIP[min(zr >> 4, 2320)])
        zr += zr_step(h)
    return z


def line_dist(h):
    return [(zz * (foot_of(h) - l)) >> 6 for l, zz in enumerate(line_z(h))]


def fade():
    t = [0xE0] + [0xE0 | (i >> 1) for i in range(16)]
    return t + [0xE0 | (0x1C - i * 0x1C // 16) for i in range(16)]


# -- driving the ROM ------------------------------------------------------------

def set_view(s, angle=None, height=None, pitch=None):
    if angle is not None:
        s.write(s.resolve("M7K_CAMERA") + CAM_ANGLE, angle & 0xFF)
    if height is not None:
        s.write(s.resolve("M7K_FLOOR") + F_HEIGHT, height)
    if pitch is not None:
        s.write(s.resolve("M7K_FLOOR") + F_PITCH, pitch & 0xFF)
    # a frame can take two vblanks: wait out the pass that read the old
    # values, then a whole one with the new
    s.wait(6)


def hdma(s):
    return s.raw("M7K_HDMA").bytes()


def floor(s):
    return s.raw("M7K_FLOOR").bytes()


def bands(s):
    return s.raw("M7K_BANDS").bytes()


def rows(s, field, k):
    """Buffer k's rows of the AB or CD stream: element 2l is line l's A
    (or C), 2l + 1 its B (or D)."""
    b = hdma(s)[field + 2 * DATA_WORDS * k:field + 2 * DATA_WORDS * (k + 1)]
    return words(b)


def band_table(s, field, stride, k):
    return list(bands(s)[field + stride * k:field + stride * (k + 1)])


def object_screen(s):
    return words(s.raw("OBJECT_SCREEN").bytes())


@pytest.fixture
def flyer(snes):
    snes.wait(30)
    return snes


# -- tables -----------------------------------------------------------------------

def test_lookup_tables(flyer):
    s = flyer
    assert words(s.raw("__M7K_SINCOS_data").bytes()) == SINCOS
    assert words(s.raw("__M7K_RECIP_data").bytes(), signed=False) == RECIP
    assert list(s.raw("__M7K_ZRECIP_data").bytes()) == ZRECIP
    assert list(s.raw("__M7K_ROW_SKY_data").bytes()) == [sky_of(h) for h in range(128)]
    assert words(s.raw("__M7K_ROW_ZR0_data").bytes(), signed=False) == [zr0(h) for h in range(128)]
    assert words(s.raw("__M7K_ROW_STEP_data").bytes(), signed=False) == [zr_step(h) for h in range(128)]
    assert list(s.raw("__M7K_FADE_data").bytes()) == fade()


# -- the floor ----------------------------------------------------------------------

def shown_table(s, field):
    """The indirect table HDMA reads this frame: `back` is the one `update`
    writes next, so the shown one is the other."""
    h = hdma(s)
    k = h[H_BACK] ^ 1
    return list(h[field + IND * k:field + IND * (k + 1)]), k


def test_floor_tables(flyer):
    s = flyer
    set_view(s, angle=0, height=64)
    f = floor(s)
    sky, ground = sky_of(64), 224 - sky_of(64)
    assert (f[F_SKY], f[F_GROUND], f[F_HEIGHT]) == (sky, ground, 64)
    assert f[F_FOOT] == foot_of(64) == ground + PITCH_DOWN
    z = line_z(64)
    assert words(f[F_LINE_Z:F_LINE_DIST], signed=False)[:len(z)] == z
    assert words(f[F_LINE_DIST:F_LINE_DIST + 448], signed=False)[:len(z)] == line_dist(64)

    # lines 0..sky hold the top matrix; line sky + r reads row r
    t, k = shown_table(s, H_ABI)
    base = s.resolve("M7K_HDMA") & 0xFFFF
    ident = base + H_TOP
    ab = base + H_AB + k * DATA_WORDS * 2
    assert t[:3] == [sky, ident & 0xFF, ident >> 8]
    assert t[3:6] == [0x80 | 127, ab & 0xFF, ab >> 8]
    assert t[6:9] == [0x80 | (ground - 127), (ab + 508) & 0xFF, (ab + 508) >> 8]
    assert t[9] == 0

    data = rows(s, H_AB, k)[:2 * ground]
    a = [(zz * 128) >> 5 for zz in z[:ground]]                # angle 0: cos7 = 128
    assert data[0::2] == a
    assert data[1::2] == [0] * ground


@pytest.mark.parametrize("angle", [10, 70, 150, 160, 200, 64, 128, 192])
def test_floor_matrix_signs(flyer, angle):
    """dizworld's signs: A = D, C = -B, from |cos| and |sin| scaled by z,
    in every quadrant and on the axes (each quadrant has its own loop)."""
    s = flyer
    set_view(s, angle=angle, height=40)
    _, k = shown_table(s, H_ABI)
    sky = sky_of(40)
    ground = 224 - sky
    z = line_z(40)[:ground]
    ab = rows(s, H_AB, k)
    cd = rows(s, H_CD, k)
    cos, sin = SINCOS[angle + 64], SINCOS[angle]
    c7, s7 = abs(cos) >> 1, abs(sin) >> 1
    for l, zz in enumerate(z):
        a = (zz * c7) >> 5
        b = (zz * s7) >> 5
        if cos < 0:
            a = -a
        if sin < 0:
            b = -b
        assert (ab[2 * l], ab[2 * l + 1], cd[2 * l], cd[2 * l + 1]) == (a, b, -b, a), l


def test_buffers_swap_and_shown_one_is_whole(flyer):
    """Each finished build is shown and the other buffer written next; the
    one HDMA reads is complete at every frame, whatever `build` is doing."""
    s = flyer
    set_view(s, angle=0, height=64)
    sky, ground = sky_of(64), 224 - sky_of(64)
    backs = set()
    for _ in range(8):
        s.wait(1)
        t, _ = shown_table(s, H_ABI)
        backs.add(hdma(s)[H_BACK])
        assert t[0] == sky and t[3] == 0x80 | 127 and t[6] == 0x80 | (ground - 127) and t[9] == 0
    assert backs == {0, 1}


def test_horizon_split(flyer):
    s = flyer
    set_view(s, angle=0, height=100)
    sky = sky_of(100)
    back = hdma(s)[H_BACK] ^ 1
    bgm = band_table(s, B_BGM, B_STRIDE, back)
    tm = band_table(s, B_TMT, B_STRIDE, back)
    ground = 224 - sky
    expect = [sky, 0x01] + ([127, 0x07, ground - 127, 0x07] if ground > 127 else [ground, 0x07])
    assert bgm[:len(expect)] == expect and bgm[len(expect)] == 0
    assert tm[:2] == [sky, 0x02] and tm[3::2][:len(expect) // 2 - 1] == [0x01] * (len(expect) // 2 - 1)
    # COLDATA is indirect: black over the sky, the ramp a byte a line, black
    col = band_table(s, B_COL, B_COL_STRIDE, back)
    black = (s.resolve("M7K_BANDS") & 0xFFFF) + B_FADE
    assert col[:3] == [sky, black & 0xFF, black >> 8]
    assert col[3:6] == [0x80 | 16, (black + 1) & 0xFF, (black + 1) >> 8]
    assert col[6:9] == [ground - 16, black & 0xFF, black >> 8] and col[9] == 0
    assert list(bands(s)[B_FADE:B_FADE + 17]) == [fade()[0]] + fade()[17:33]


def test_floor_projection(flyer):
    """Unrotated, the camera at (512, 512): an object straight ahead lands
    in the center column on the line whose distance is nearest below its
    own; one behind the camera is hidden."""
    s = flyer
    set_view(s, angle=0, height=64)
    sky = sky_of(64)
    ground = 224 - sky
    z = line_z(64)
    dist = line_dist(64)[:ground]
    pos = object_screen(s)
    for i in range(5):
        f, r = 512 - OBJECT_Y[i], OBJECT_X[i] - 512
        sx, sy = pos[2 * i], pos[2 * i + 1]
        if f <= 0 or f > dist[0] or f < dist[-1]:
            assert sy == HIDDEN, i
            continue
        line = next(l for l in range(ground) if dist[l] <= f)
        assert sy == sky + line, i
        assert abs(sx - (128 + r * RECIP[z[line]] // 256)) <= 1, i


def screen(s, tmp_path, name):
    return s.screenshot(tmp_path / f"{name}.png").read_bytes()


def test_vertical_flip_dropped_on_floor_but_kept(flyer, tmp_path):
    """The per-line matrices follow the real scanline, so the floor writes
    M7SEL without the vertical bit: the picture doesn't change. The bit
    stays in the transport's state, for a return to Static mode; a horizontal
    reflection does show."""
    s = flyer
    sel = s.resolve("M7K_HDMA") + H_SEL
    s.wait(4)
    plain = screen(s, tmp_path, "plain")
    s.write(sel, 0x02)
    s.wait(4)
    assert hdma(s)[H_SEL] == 0x02
    assert screen(s, tmp_path, "vertical") == plain
    s.write(sel, 0x01)
    s.wait(4)
    assert screen(s, tmp_path, "horizontal") != plain


# -- pitch ------------------------------------------------------------------------

@pytest.mark.parametrize("pitch,shown", [(0, 0), (-32, -32), (64, 64), (-60, -32), (100, 64)])
def test_pitch_moves_the_split(flyer, pitch, shown):
    """The horizon is 32 + h/2 + pitch, the pitch clamped to -32..64, in the
    state, the floor's indirect table and the BGMODE split alike."""
    s = flyer
    set_view(s, angle=0, height=64, pitch=pitch)
    f = floor(s)
    sky = sky_of(64) + shown
    ground = 224 - sky
    assert (s16(f[F_PITCH] << 8) >> 8, f[F_SKY], f[F_GROUND]) == (shown, sky, ground)
    t, k = shown_table(s, H_ABI)
    entries, i, lines = [], 0, 0
    while t[i]:
        entries.append(t[i]); lines += t[i] & 0x7F; i += 3
    assert lines == 224 and sum(e & 0x7F for e in entries if e < 0x80) == sky
    bgm = band_table(s, B_BGM, B_STRIDE, k)
    sky_lines = sum(bgm[j] for j in range(0, 12, 2) if bgm[j] and bgm[j + 1] == 0x01)
    assert sky_lines == sky


def test_pitch_leaves_the_line_tables(flyer):
    """Line l counts from the horizon: z(l) and dist(l) are the same at
    every pitch, and only the pivot follows it."""
    s = flyer
    tables = []
    for pitch in (-32, 0, 64):
        set_view(s, angle=0, height=64, pitch=pitch)
        f = floor(s)
        tables.append(f[F_LINE_Z:F_LINE_DIST + 448])
        sky = sky_of(64) + pitch
        assert word(f, F_VOFS) & 0xFFFF == (word(f, F_CY) - (sky + foot_of(64))) & 0xFFFF
    assert tables[0] == tables[1] == tables[2]


def test_pitch_moves_projection_by_whole_lines(flyer):
    """A floor point visible at pitch 0 and at pitch p keeps its sx and
    moves exactly p lines down."""
    s = flyer
    set_view(s, angle=0, height=64, pitch=0)
    flat = object_screen(s)
    moved = 0
    for pitch in (-32, 20, 64):
        set_view(s, angle=0, height=64, pitch=pitch)
        pos = object_screen(s)
        for i in range(5):
            if flat[2 * i + 1] == HIDDEN or pos[2 * i + 1] == HIDDEN:
                continue
            assert (pos[2 * i], pos[2 * i + 1]) == (flat[2 * i], flat[2 * i + 1] + pitch), (pitch, i)
            moved += 1
    assert moved


def test_pitch_buttons(flyer):
    """X looks up and B looks down, two lines a frame, held at the limits."""
    s = flyer
    s.hold("x", frames=60).wait(2)
    assert floor(s)[F_PITCH] == PITCH_UP
    s.hold("b", frames=80).wait(2)
    assert s16(floor(s)[F_PITCH] << 8) >> 8 == -PITCH_DOWN
