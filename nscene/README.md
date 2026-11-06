# nscene

Scenes for SNES games written in [R65](https://github.com/BubbleZapGames/R65):
a title screen, a level, a pause box, a game-over page. Each scene is a type
that implements the `Scene` trait. A `SceneController` runs the frame loop and
the NMI. It also navigates between scenes and runs the transitions from one to
the next.

Scenes and transitions share one base trait, `SceneHooks`, with the two hooks
that run every frame: `update` in the main loop and `nmi` in vblank. The
controller calls them on whichever is running, the current scene or the
transition to or from it.

A scene's hooks take no `self`. A scene is a type, usually an empty struct or
the struct its state lives in, and its state is a static the hooks name
directly, so a field read is one absolute load. A request names types:
`SceneController::transition!(Game, FadeOut, FadeIn)`, or `goto!(Game)` with
no transitions. The controller holds the
running hooks as function pointers and calls each one in place, a
`JML [hook]`, whatever the phase.

There is one controller, which nscene owns: the game drives it through
associated functions and macros, and declares no controller of its own.
Including nscene costs no RAM by itself: a static nothing uses is dropped at
compile time.

The controller never touches the PPU. Brightness, mosaic and the rest belong
to the scenes and the transitions; `transitions.r65` has ready-made fades,
mosaics and cuts.

| Event | Hook | Runs |
|---|---|---|
| Load | `load` | once, when the scene comes on screen |
| Main loop | `update` | once per frame while the scene is Active |
| NMI | `nmi` | in vblank, after each completed frame, while the scene is Active |
| Transition In | `update` and `nmi` of the In transition named in the request | once per frame until its `done` returns `true` |
| Transition Out | `update` and `nmi` of the Out transition named in the request | once per frame until its `done` returns `true` |
| Unload | `unload` | once, as the scene leaves |

## Why

Without a scene layer, every game builds the same machinery by hand:

- A state byte with `if state == ...` chains in the update, the draw, and the
  vblank work.
- The "on enter" code repeated at every site that changes state.
- Fade counters in one-off globals.
- Screen changes as hard cuts through force blank.
- HDMA, colour math and windows left set by one screen for the next to trip
  over.

nscene puts each screen's code in its `impl` blocks, and every change goes through
the same lifecycle, with a place for each step: a scene sets up its PPU state
in `load` and undoes it in `unload`.

## Quick start

```toml
# r65.toml
[dependencies]
stdlib = { git = "https://github.com/BubbleZapGames/R65", version = "0.1" }
nscene = { git = "https://github.com/BubbleZapGames/r65-packages", version = "0.1" }
```

```rust
include!("stdlib/sneslib.r65")
include!("nscene/nscene.r65")
include!("nscene/transitions.r65")      // optional: fades, mosaics, cuts

#[bank(0)]

scene_fade_in!(FadeIn, 30);             // transition types, their length built in
scene_fade_out!(FadeOut, 30);

struct Title { blink: u8 }
static mut TITLE: Title;                // the scene's state

impl SceneHooks for Title {
    fn update() {
        TITLE.blink++;
        if start_pressed() {
            SceneController::transition!(Game, FadeOut, FadeIn);
        }
    }

    fn nmi() { }                        // no vblank work
}

impl Scene for Title {
    fn load() {
        // The fade out left force blank on: DMA tiles, map and palette freely.
        TITLE.blink = 0;
    }

    fn unload() { }
}

#[entry]
fn reset() -> ! {
    snes_init();
    SceneController::transition!(Title, SceneNone, FadeIn);   // the first scene
    SceneController::run();
}

#[interrupt(nmi)]
fn vblank() {
    SceneController::nmi!();
}
```

A scene implements two traits, in two `impl` blocks: `SceneHooks` (`update`
and `nmi`, both required; one with nothing to do has an empty body) and
`Scene` (`load` and `unload`, both required).
Transitions are not tied to a scene: each `transition!` names the two it runs.

- **No setup call.** The controller is set up by its static initializer,
  before the `#[entry]` body runs and so before `snes_init` turns the NMI on:
  `SceneEmpty`, which does nothing, with nothing pending. The first scene is an ordinary
  `transition!` or `goto!`, made before `run()`.
- **A scene's state is a static of the game's**, anywhere in RAM. A scene
  with no state needs none: `struct Fallen;` and its `impl`s are the whole
  scene. Its hooks name the static: `TITLE.blink`, not `self.blink`.
- **Scene code can live in any bank.** Every hook is called as a far
  function.
- **A scene needs no initializer.** `load` sets its state.

`example/` is a complete ROM with four scenes and every event. Its
`tests/` drive it in Mesen.

## Events

There is one current scene. It receives events only while it is Active: during its transitions, the transition's `update` and `nmi` run
instead. Every hook except `nmi` runs in the main loop. `update` and `nmi`
come from `SceneHooks`, the rest from `Scene`.

| Hook | When | Guarantees |
|---|---|---|
| `load()` | Brought on screen by `goto!` or `transition!` | No `nmi` runs until the In transition starts. The screen is as the Out transition left it: after a ready-made fade or mosaic, force blank, so DMA freely, over as many frames as it takes. With no Out (`SceneNone`), the screen is still lit. |
| `update()` | Each frame while Active | The place for game logic and for navigation requests. Not called during a transition. |
| `nmi()` | Each vblank after a completed frame, while Active | Never on a lag frame, never during a transition. Keep it to VRAM, CGRAM and OAM uploads. |
| `unload()` | After Transition Out, when the scene is left | Undo the PPU state `load` set up that the next scene won't set for itself: HDMA, colour math, windows. |

## Navigation

```rust
SceneController::transition!(Over, MosaicOut, FadeIn);   // change to Over through two transitions
SceneController::goto!(Over);                            // change to Over with none
```

There are two requests, both naming the next scene as a type.
`transition!` also names two [transitions](#transitions): the Out takes the
current scene off screen and the In brings the next one on.

Either can be `SceneNone`, for no transition: the controller skips it, so it
moves straight on and the screen stays as it is. The game's first request has
no scene to take off screen, so its Out is always `SceneNone`. `goto!(Next)`
does what `transition!(Next, SceneNone, SceneNone)` does, without storing
any transition: the scene changes at the frame boundary, and a scene that comes in that way turns the screen on itself, in
`load`:

```rust
SceneController::goto!(Title);                           // Title's load sets INIDISP
```

A request is recorded, not acted on. It takes effect at the start of the next
frame, so the rest of the current `update` still runs. A request is a
`bool`, `false` when it is refused: while a transition is under way, or when
another request is already pending (the first request wins).

The lifecycle:

```
Active ──request──▶ Out ──Out done──▶ In ──In done──▶ Active
                                │
               the current scene's unload, then Next::load()
```

A scene that wants a timer counts frames in its own `update`.

## The NMI handshake

`SceneController::run()` loops forever:

1. Move the lifecycle on: start an Out for a pending request, or, when the
   running transition's `done` says so, unload and load between Out and In,
   or go Active after In.
2. Call `update` on whatever is running: the current scene, or the transition.
3. Mark the frame done (`frame_done`), and wait until the NMI has taken it.

`SceneController::nmi!()`, the body of the NMI handler, acknowledges the NMI.
If the frame is done, it calls `nmi` on whatever is running and clears the
`frame_done` flag.

If the frame is not done, it counts a lag frame in `SCENE_CONTROLLER.lag` and does
nothing else. That count is every NMI that found no finished frame: an
`update` that overran, but also each NMI while a `load` runs, since it may
take several frames, and those before `run` steps its first frame. It is never
reset, and wraps at 65535; compare two readings.

This gives three guarantees:

- **A lag frame uploads nothing.** If `update` overruns vblank, `nmi` is skipped
  rather than run on a half-built frame. It runs once the frame is complete,
  so every `update` is followed by exactly one `nmi`.
- **The NMI never sees a scene half switched in.** What it calls changes only
  while the frame is not done.
- **A transition's `nmi` runs in vblank.** It writes PPU registers directly,
  and nothing it writes tears.

`nmi!` calls no hook before `run` has stepped a frame: the static initializer
clears `frame_done` before `snes_init` turns the NMI on. The controller
relies on `snes_init` (or your own setup) for NMI and auto-joypad.

**Reading the pad.** `update` starts early in vblank, while the auto-joypad read
may still be running. Call `wait_autojoy!()` before reading `JOY1L`/`JOY1H`,
otherwise you read a half-shifted value.

## Transitions

A transition is a type that implements two traits:

```rust
trait SceneHooks {                      // shared with Scene
    fn update();                        // main loop, once per frame
    fn nmi();                           // vblank, after that frame's update
}

trait SceneTransition: SceneHooks {
    fn done() -> bool;                  // true ends it
}
```

All three hooks are required: a transition with nothing to do in one writes an
empty body, so every transition states its whole behaviour.

When a transition starts, the controller sets its frame counter to 0, then
each frame calls `update` and `nmi`, until `done` returns `true`. Setup a
transition needs is its first frame's work: `frame!() == 0` in `update`.
The counter is `SceneController::frame!()`: 0 in the first `update` and
`nmi`, 1 in the second, and so on. The controller keeps it as a stdlib `U32`,
`SCENE_CONTROLLER.frame`; `frame!()` is its low word, a `u16`, which is all a
transition up to 65535 frames long needs. Only one transition runs at a time, so
this one counter is every transition's clock, and a transition needs no RAM
of its own. `done` is asked at the start of
each frame from the second on, so the first `update` and `nmi` always run: a
transition that finishes in one frame returns `true` every time. The split
gives heavy work a place outside vblank: `update` can work out a palette and
`nmi` only upload it. While it runs, the scene's own hooks don't, so the world
holds still; a transition that should animate the scene does that itself.

A transition is chosen per request, not per scene, so the same scene can
arrive one way from the title and another from a pause.

`transitions.r65` is optional and has nothing to do with the controller beyond
the trait. Its macros each define a transition type with its length, 1 to 255
frames, built in:

| Macro | Effect |
|---|---|
| `scene_fade_in!(Type, frames)` | Brightness 0 to 15 over `frames` frames. |
| `scene_fade_out!(Type, frames)` | Brightness 15 to 0 over `frames` frames, then force blank. |
| `scene_mosaic_in!(Type, frames)` | Mosaic shrinks from 16 pixels to 1 on every BG while the screen fades up. |
| `scene_mosaic_out!(Type, frames)` | Mosaic grows from 1 pixel to 16 while the screen fades down, then force blank. |

```rust
scene_fade_out!(FadeOut90, 90);         // a fade out that lasts 90 frames
scene_fade_in!(FadeIn, 30);
```

A type needs no RAM and no data: its length is a constant in its code. Each
one is its own code, about 135 bytes of ROM for a fade and 160 for a mosaic,
so a game with many lengths of one kind pays for each; a type nothing uses is
dropped. The level each frame is `frame * 15 / frames`, one hardware divide.

| Type | Effect |
|---|---|
| `SceneCut` | One frame, screen left lit. |
| `SceneCutBlank` | One frame: force blank. |

These two have no settings, so `transitions.r65` defines them once, for every
request to name.

### Sepia

`scene_sepia_out!(Type, PALETTE)` defines a transition type that turns every colour
to a sepia tone over 32 frames and leaves the screen lit: the Out transition
to a game-over scene that loads nothing, so the game's picture stays on
screen beneath it. A tone comes from the green channel
alone, at five eighths of its level (at least 4), with blue at half that, and
each frame every channel steps one level toward it.

```rust
#[ram]
static mut SEPIA: ScenePalette;         // 1 KB: the palette on screen and its tones
scene_sepia_out!(SepiaOut, SEPIA);

SceneController::transition!(GameOver, SepiaOut, SceneCut);
```

Its first `nmi` reads the palette back from CGRAM, so it works on whatever is
on screen. From then on its `update` steps all 256 colours in the main loop,
and its `nmi` only uploads them with DMA channel 0: in the example the NMI
takes about 4 scanlines.

Once the game-over scene is current, the game's `nmi` no longer runs, so the
sepia holds. To leave, `transition!` through a fade that blanks, to a scene whose
`load` sets its own palette.

### A length set at run time

A length is any `u8` expression, read every frame. For one decided at run
time (a speed option, timing read from data), name a static and set it
before the request:

```rust
static mut SPEED: u8;
scene_fade_in!(FadeInBy, SPEED);

SPEED = SPEED_SETTING;
SceneController::transition!(Title, FadeOut, FadeInBy);
```

Set it only for a request that will be accepted: writing it while the
transition runs changes its length mid-way. A scene's `update` never runs
during a transition, so setting it there just before the request is safe.

### A transition of your own

`scene_frames_transition!(Type, step, out, frames)` makes a type of the same
shape as the fades: done once the controller's frame passes `frames`. `step`
is a macro of yours that draws one frame, `step!(frame, length, out)`, run
from `nmi`, writing the end state from frame `length` on, as
`scene_fade_nmi!` and `scene_mosaic_nmi!` do:

```rust
macro_rules! wipe_nmi($t:expr, $length:expr, $out:expr) { /* WH0/WH1 from $t */ }
scene_frames_transition!(Wipe, wipe_nmi, true, 20);
```

A transition undoes only what it set: the mosaics end with MOSAIC off. The
rest of the PPU state belongs to the scenes. One that turns on HDMA, colour
math or windows turns them off in `unload`, so the next scene doesn't
inherit them:

```rust
impl Scene for Level {
    fn load()    { /* ... */ HDMAEN = 0x04; }   // a gradient on channel 2
    fn unload()  { HDMAEN = 0; }
}
```

Mode, BG addresses, scroll and the layer enables need no undoing: every `load`
sets those for itself anyway.

INIDISP and MOSAIC are write-only, and nscene keeps no copy of them.

Any other custom transition is a type of your own, reading
`SceneController::frame!()` for its clock; one with state keeps it in a
static. One that finishes in a frame does its work in `nmi`:

```rust
struct HalfDim;

impl SceneHooks for HalfDim {
    fn update() { }
    fn nmi() { INIDISP = 8; }
}

impl SceneTransition for HalfDim {
    fn done() -> bool { return true; }
}
```

## A scene drawn over the last one

A scene that comes in without blanking, such as a game-over page over the
game, is a `transition!` whose transitions keep the screen lit and whose `load`
writes no VRAM, CGRAM or OAM: the picture the last scene left stays on
screen, and the new scene draws over it in `nmi`.

```rust
struct GameOver;

impl SceneHooks for GameOver {
    fn update() {
        if start_pressed() { SceneController::transition!(Title, FadeOut, FadeIn); }
    }
    fn nmi() { /* draw the box into BG3 here, in vblank */ }
}

impl Scene for GameOver {
    fn load() { }                       // the screen stays lit: no VRAM work here
    fn unload() { }
}

SceneController::transition!(GameOver, SceneCut, HalfDim);    // HalfDim from above
```

The scene left behind is unloaded, not kept: there is no stack to return to
it. A scene that should come back where it was keeps its state in its static
and reloads its VRAM in `load`, through a transition that blanks.

## Cost

Every frame the controller makes two indirect calls: `update` from the main
loop and `nmi` from the NMI, on the current scene or on the running
transition. A
transition adds a `done` call per frame. Each is
a far call through a pointer held in low RAM, `PHK / PEA / JML [hook]`,
14 cycles there and 6 for the `RTL` back, with no dispatch table and no
pointer to `self`. A hook then reads its state with absolute addressing.

`nmi!` is a macro, so its body is always inlined into the NMI handler: the
only call in vblank is the `nmi` hook itself.

A request expands, through the `SceneController::request!` macro, to a check
that the controller is Active and then stores of the hooks of the types it
names, written as immediates with no call: for `transition!` 10 function
addresses, about 170 bytes of ROM at each request site; for `goto!` only the
scene's 4, about 80. The controller keeps
the current scene's four hooks itself, and `SceneController::install()`
copies the incoming scene's over them.

Memory, all of it only if used:

- nscene's controller, `SCENE_CONTROLLER`: 50 bytes of low RAM (the
  current and the incoming scene's hooks, both transitions', and the `U32`
  frame counter, the clock of every transition), and 50 of ROM for its
  initializer;
- each scene: its state, if it has any, wherever the game puts it;
- each transition type: no RAM, and its own code in ROM (the fades and
  mosaics above).

## Requirements

- An R65 compiler with associated trait functions: trait methods without
  `self`, `Type::name` as a function value, and function addresses in a
  static's initializer. Built with `--cfg snes`
  (`cfg = ["snes"]` in `[bin]`).
- Hooks are called on the type, never on a value: `Game::update()`, not
  `GAME.update()`, which is an error.
- The Default ABI.
- The game's NMI handler is `SceneController::nmi!()`. Do any other vblank
  work in the current scene's `nmi`.
- Public names: `SceneHooks`, `Scene`, `SceneTransition`, `SceneController`,
  `SceneHookSet`, `SceneTransitionHookSet`, `ScenePhase`, `SceneNone`, `SceneEmpty`, `SceneCut`, `SceneCutBlank`,
  `ScenePalette`, `SCENE_CONTROLLER`, `scene_*`
  (macros).
