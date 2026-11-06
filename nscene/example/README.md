# nscene example

A ROM with four scenes that exercises every nscene event:

```
Title --Start--> Game --Select--> Over --Start--> Title
                      --Y--> Fallen --Start--> Title
```

nscene owns the controller (`SCENE_CONTROLLER`) and the cuts (`SceneCut`).
Each scene is a type with an `impl SceneHooks` and an `impl Scene` in
`src/main.r65`; Game, the one
with state, keeps it in the static `GAME`, which its hooks read by name. The
transitions are types made by nscene's macros (`scene_fade_in!(FadeIn, 30)`,
`scene_mosaic_out!(MosaicOut, 30)`, and so on), their lengths built in.

- **Title** and **Over** come and go with fades. Title's Start makes a second
  request in the same frame, a `goto!(Over)`, to show it refused: the first
  request wins. Over comes in with a
  60-frame fade (`SlowFadeIn`, a second type of the same kind as `FadeIn`)
  and leaves through `LeaveFade`, whose length is the static `LEAVE_FRAMES`,
  set to 90 just before the request.
- **Game** draws a checkerboard on BG1, cycles the backdrop from its `nmi`,
  and enters and leaves through a mosaic. Its `nmi` stops while its
  transitions run, so the backdrop holds still. Hold B to make `update`
  overrun the frame and watch `SCENE_CONTROLLER.lag` climb.
- **Fallen** is a game-over page over Game's picture, as in classickong:
  reached with `SepiaOut` (`scene_sepia_out!`, its work area the `#[ram]`
  static `SEPIA`) and no In transition, it turns Game's picture sepia and
  leaves it lit, since Fallen loads nothing. Start fades to Title.
  The sepia steps its colours in `update` and only uploads them in `nmi`; the
  NMI records the most scanlines it has taken in `NMI_LINES_MAX`, which the
  test checks stays under 20.

```bash
make                     # fetch dependencies (nscene by path, stdlib from git) and build build/NSCENE.smc
pytest tests             # drive the ROM in Mesen-GDB (pip install -e Mesen-GDB/python)
```
