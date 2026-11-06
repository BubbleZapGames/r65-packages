"""The nscene lifecycle, driven through the example ROM.

INIDISP and MOSAIC are write-only and nscene keeps no copy of them, so the
transitions are checked on screen: brightness is the brightest channel of a
frame, and the mosaic shows in Game's BG1 checker, whose runs are 4 pixels
wide unmosaicked.
"""
from PIL import Image

from states import game, title

# SceneController field offsets (packed, declaration order): the current
# scene's hooks first (update, nmi, load, unload).
CURRENT, PHASE, LAG = 0, 42, 44
UNLOAD = CURRENT + 9    # current.unload: transitions never replace it
ACTIVE = 0          # ScenePhase::Active
ROWS = range(16, 64)  # picture rows (the screenshot has a blank border above)


def scenes(s):
    b = s.raw("SCENE_CONTROLLER").bytes()
    return {
        "cur": b[UNLOAD] | b[UNLOAD + 1] << 8 | b[UNLOAD + 2] << 16,
        "phase": b[PHASE],
        "lag": b[LAG] | b[LAG + 1] << 8,
    }


def addr(s, scene):
    """The controller holds the current scene as its hooks. Its `update`
    and `nmi` are the transition's while one runs, so `unload` names it."""
    return s.resolve(f"{scene}__unload")


def ticks(s):
    return s.u16("GAME")                   # Game.ticks, its first field


def look(s):
    """(brightness, runs) of the current frame: the brightest channel, and
    the lengths of the checker's white runs along ROWS (white is the one
    grey; Game's backdrop always has some green and no blue). A coarse
    mosaic can leave a row all backdrop, so it takes a band of rows, and a
    run cut off by the right edge is left out."""
    im = Image.open(s.screenshot()).convert("RGB")
    bright = max(hi for _, hi in im.getextrema())
    runs = []
    for y in ROWS:
        n = 0
        for x in range(im.width):
            r, g, b = im.getpixel((x, y))
            if r == g == b and r > 0:
                n += 1
            elif n:
                runs.append(n)
                n = 0
    return bright, runs


def watch(s, frames):
    seen = []
    for _ in range(frames):
        s.run(1)
        seen.append(look(s))
    return seen


def clean(runs):
    return bool(runs) and all(n == 4 for n in runs)


def blocky(runs):
    return bool(runs) and min(runs) >= 8         # a mosaic of 8 pixels or more


def settled(s, name):
    c = scenes(s)
    assert c["cur"] == addr(s, name)
    assert c["phase"] == ACTIVE


def test_boot_fades_title_in(snes):
    levels = [b for b, _ in watch(snes, 50)]
    lit = [v for v in levels if v]
    assert lit == sorted(lit), levels                # a ramp, never down
    assert lit[0] < lit[-1] // 3 and levels[-1] == levels[-2], levels
    settled(snes, "Title")


def test_goto_game_mosaics_in(state):
    s = state(title)
    s.start()
    seen = watch(s, 80)                              # Title fades out, Game mosaics in
    lit = [(b, runs) for b, runs in seen if runs]
    assert blocky(lit[0][1]), lit[:3]                # comes in coarse
    assert all(clean(runs) for _, runs in seen[-10:]), seen[-10:]
    levels = [b for b, _ in lit]
    assert levels == sorted(levels), levels          # fading up while it sharpens
    settled(s, "Game")
    before = ticks(s)
    s.wait(10)
    assert ticks(s) == before + 10


def test_lag_frames_skip_nmi(state):
    s = state(game)
    c0, calls0, nmi0 = scenes(s), s.u16("GAME_NMI_CALLS"), s.u16("NMI_CALLS")
    s.b(60)                                          # update overruns while B is held
    c1, calls1, nmi1 = scenes(s), s.u16("GAME_NMI_CALLS"), s.u16("NMI_CALLS")
    nmis, lagged = nmi1 - nmi0, c1["lag"] - c0["lag"]
    assert lagged > 0
    assert calls1 - calls0 == nmis - lagged          # the hook never runs on a lag frame


def test_scene_nmi_stops_for_its_transition(state):
    s = state(game)
    calls = s.u16("GAME_NMI_CALLS")
    s.wait(10)
    assert s.u16("GAME_NMI_CALLS") == calls + 10     # Active: once per frame
    s.select().run(3)                                # Game is mosaicking out
    calls = s.u16("GAME_NMI_CALLS")
    s.run(20)
    assert scenes(s)["phase"] != ACTIVE
    assert s.u16("GAME_NMI_CALLS") == calls          # only the transition's hooks run


def test_goto_over_and_back_to_title(state):
    s = state(game)
    s.select()
    out = watch(s, 40)                               # Game mosaics out to black
    assert clean(out[0][1]), out[0]
    lit = out[:[b for b, _ in out].index(0)]
    assert blocky(lit[-1][1]), lit[-3:]              # leaves coarse
    levels = [b for b, _ in lit]
    assert levels == sorted(levels, reverse=True), levels

    levels = [b for b, _ in watch(s, 80)]            # Over comes in with SlowFadeIn
    lit = [v for v in levels if v]
    ramp = lit[:lit.index(max(lit))]
    assert ramp == sorted(ramp) and len(ramp) > 40, levels   # a level per 4 frames, not 2
    settled(s, "Over")

    s.start()                                        # leaves with LeaveFade, LEAVE_LENGTH 90
    levels = [b for b, _ in watch(s, 100)]
    dark = levels.index(0)
    assert 85 <= dark <= 95, levels                  # lit for 90 frames
    assert levels[:dark] == sorted(levels[:dark], reverse=True), levels
    s.wait(40)
    settled(s, "Title")


def test_second_request_in_a_frame_is_refused(state):
    """Title asks for Game, then at once for Over with goto!: the second is
    refused, and Game is what arrives."""
    s = state(title)
    s.start().run(4)                                 # Title is fading out
    c = scenes(s)
    assert c["phase"] != ACTIVE
    assert c["cur"] == addr(s, "Title")
    assert s.u8("SECOND_REQUEST_REFUSED") == 1
    s.wait(80)
    settled(s, "Game")


def brightest(s):
    """The brightest colour along ROWS: the checker's white, wherever it has
    got to."""
    im = Image.open(s.screenshot()).convert("RGB")
    return max((im.getpixel((x, y)) for y in ROWS for x in range(im.width)), key=sum)


def test_fallen_turns_game_sepia(state):
    s = state(game)
    s.y()
    seen = []
    for _ in range(40):
        s.run(1)
        seen.append(brightest(s))
    assert all(sum(c) > 0 for c in seen), seen      # never blanked
    r, g, b = seen[-1]
    assert r == g and 0 < b < g * 0.6, seen[-1]      # white became sepia
    assert seen[0][0] == seen[0][1] == seen[0][2], seen[0]     # began grey
    assert len(set(seen)) >= 15, seen                # a step at a time, not a cut
    settled(s, "Fallen")                             # Active with no In transition
    assert s.u16("NMI_LINES_MAX") < 20              # stepped in update; the NMI only uploads

    s.start().wait(70)                               # fades out, Title fades in
    settled(s, "Title")
