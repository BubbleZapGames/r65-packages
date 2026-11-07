"""mode7kit's split screen, driven through the split example ROM: two floor
instances over one transport, four bands, four views.

Each test writes the cameras and lets the frame run. M7A-D, M7X/M7Y and the
scrolls are write-only, so what reaches the screen is checked by
screenshot, a half at a time; the tables by their state.
"""
import io

import pytest
from PIL import Image

CAM_X, CAM_Y, CAM_ANGLE = 0, 2, 4                     # M7Camera
F_SKY, F_GROUND = 3, 4                                # M7Floor, FloorB
H_BACK, H_HDMAEN = 9, 11                              # M7HDMA
V_CTR, V_SCR, V_STRIDE = 37, 119, 41                  # M7Views (4 views)
HALF = 112
TOP_ROW = 7                                           # screen line 0 in a screenshot


def sky_of(h):
    return 32 + (h >> 1)


def set_cam(s, name, x=None, y=None, angle=None):
    base = s.resolve(name)
    if x is not None:
        s.write(base + CAM_X, (x << 6) & 0xFFFF, 2)
    if y is not None:
        s.write(base + CAM_Y, (y << 6) & 0xFFFF, 2)
    if angle is not None:
        s.write(base + CAM_ANGLE, angle & 0xFF)
    s.wait(6)


def halves(s, tmp_path, name):
    img = Image.open(s.screenshot(tmp_path / f"{name}.png")).convert("RGB")
    top = img.crop((0, TOP_ROW, 256, TOP_ROW + HALF)).tobytes()
    bottom = img.crop((0, TOP_ROW + HALF, 256, TOP_ROW + 224)).tobytes()
    return top, bottom


@pytest.fixture
def split(snes):
    snes.wait(30)
    return snes


def test_channels(split):
    """Matrix on 2-3, BGMODE and TM on 4-5 (no COLDATA), views on 1 and 7."""
    s = split
    assert s.raw("M7K_HDMA").bytes()[H_HDMAEN] == 0xBE


def test_each_half_follows_its_camera(split, tmp_path):
    """Turning the bottom camera changes only the bottom half, and moving
    the top one only the top half."""
    s = split
    top0, bottom0 = halves(s, tmp_path, "start")
    set_cam(s, "CAM_B", angle=128 + 40)
    top1, bottom1 = halves(s, tmp_path, "turn_b")
    assert top1 == top0 and bottom1 != bottom0
    set_cam(s, "M7K_CAMERA", x=600, y=420)
    top2, bottom2 = halves(s, tmp_path, "move_a")
    assert bottom2 == bottom1 and top2 != top1


def same_pixels(a, b):
    return sum(1 for i in range(0, len(a), 3) if a[i:i + 3] == b[i:i + 3]) / (len(a) // 3)


def test_same_camera_same_picture(split, tmp_path):
    """Both cameras in one place and heading: each half shows the same
    view, the bottom's 112 lines lower. The skies match exactly; the floors
    match but for sub-texel rounding, since Mode 7 truncates its y term and
    its VOFS - CY term to 1/64 separately and the halves split the same sum
    differently. Different headings don't come close."""
    s = split
    sky = sky_of(64) - 24
    set_cam(s, "M7K_CAMERA", x=512, y=512, angle=30)
    set_cam(s, "CAM_B", x=512, y=512, angle=30)
    top, bottom = halves(s, tmp_path, "same")
    line = 256 * 3
    assert top[:sky * line] == bottom[:sky * line]
    assert same_pixels(top[sky * line:], bottom[sky * line:]) > 0.9
    set_cam(s, "CAM_B", angle=90)
    top, bottom = halves(s, tmp_path, "apart")
    assert same_pixels(top[sky * line:], bottom[sky * line:]) < 0.5


def test_horizons_and_bands(split):
    """Each floor's horizon sits in its own half (the pitch -24 at height
    64); the BGMODE table switches 1, 7, 1, 7 at the two horizons."""
    s = split
    a, b = s.raw("M7K_FLOOR").bytes(), s.raw("FLOOR_B").bytes()
    sky = sky_of(64) - 24
    assert (a[F_SKY], a[F_GROUND]) == (sky, HALF - sky)
    assert (b[F_SKY], b[F_GROUND]) == (HALF + sky, HALF - sky)
    k = s.raw("M7K_HDMA").bytes()[H_BACK] ^ 1
    stride = 4 * 4 + 1
    bgm = list(s.raw("BANDS4").bytes()[14 + stride * k:][:stride])   # after count, 3x4 layout, haze
    entries = [(bgm[i], bgm[i + 1]) for i in range(0, stride - 1, 2) if bgm[i]]
    assert entries == [(sky, 0x01), (HALF - sky, 0x07), (sky, 0x01), (HALF - sky, 0x07)]


def test_views(split):
    """The views' tables: per band its lines and BG1 scroll; the floors'
    scroll is their own, the skies' puts a 240-line sky's bottom on the
    half's horizon."""
    s = split
    set_cam(s, "M7K_CAMERA", x=512, y=512, angle=0)
    set_cam(s, "CAM_B", x=300, y=700, angle=64)
    v = s.raw("M7K_VIEWS").bytes()
    k = s.raw("M7K_HDMA").bytes()[H_BACK] ^ 1
    scr = v[V_SCR + V_STRIDE * k:V_SCR + V_STRIDE * (k + 1)]
    ctr = v[V_CTR + V_STRIDE * k:V_CTR + V_STRIDE * (k + 1)]
    sky = sky_of(64) - 24
    rows = [scr[i:i + 5] for i in range(0, 20, 5)]
    word = lambda b, o: b[o] | b[o + 1] << 8
    assert [r[0] for r in rows] == [sky, HALF - sky, sky, HALF - sky] and scr[20] == 0
    assert (word(rows[0], 1), word(rows[0], 3)) == (0, 240 - sky)
    assert (word(rows[2], 1), word(rows[2], 3)) == ((-(64 << 2)) & 0x3FF, 240 - (HALF + sky))
    assert word(rows[1], 1) == (512 - 128) & 0xFFFF            # hofs = cx - 128
    assert word(rows[3], 1) == (300 - 128) & 0xFFFF
    assert (word(ctr, 5 + 1), word(ctr, 5 + 3)) == (512, 512)  # floor A's center
    assert (word(ctr, 15 + 1), word(ctr, 15 + 3)) == (300, 700)
