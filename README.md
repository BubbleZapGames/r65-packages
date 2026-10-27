# r65-packages

General-purpose libraries for [R65](https://github.com/BubbleZapGames/R65),
the Rust-inspired language for 65816 and SNES development.

This is one git repository holding many packages. Each package has its own
version and release tags, so releasing one never forces a release of another.
A project depends on the packages it wants, by name, through its `r65.toml`.

Packages need r65 0.3.0 or later, the first release with package support.

## Packages

None are released yet.

| Package | Description |
|---|---|

## Using a package

Add a package to your project's `r65.toml` under `[dependencies]`, by its name:

```toml
[dependencies]
tween = { git = "https://github.com/BubbleZapGames/r65-packages", version = "0.2" }
```

Or let `r65pkg` write that line for you. It picks the newest release and locks it:

```bash
r65pkg add tween --git https://github.com/BubbleZapGames/r65-packages
```

Then include the package's files by its name:

```rust
include!("tween/tween.r65")
```

`make` in a project from `r65x init` fetches dependencies through
`r65pkg fetch`. To fetch them by hand, run `r65pkg fetch` yourself.
`r65pkg tree` shows what a project uses.

## Versions

A `version` is a requirement with Cargo's caret meaning:

| Requirement | Accepts |
|---|---|
| `"0.2"` | `0.2.0` up to, but not including, `0.3.0` |
| `"0.2.3"` | `0.2.3` up to, but not including, `0.3.0` |
| `"1.4"` | `1.4.0` up to, but not including, `2.0.0` |
| `"=0.2.3"` | exactly `0.2.3` |

A build holds one version of each package. When several packages require
the same one, the newest release that satisfies all of them wins. If no
release satisfies them all, the build fails with an error that names each
requirement.

`r65.lock` records the exact commit used. Commit it with your project.
`r65pkg update` moves to the newest releases your requirements allow, and
`r65pkg update tween` updates a single package.

You can pin a dependency with `tag`, `rev` or `branch` in place of `version`.
Do that only when you have to. A pin works alongside other packages'
requirements only while its version satisfies them, and two different pins
of one package never work together.

## Layout

```
r65-packages/
├── r65.toml          # [workspace] listing every package
├── tween/
│   ├── r65.toml      # the package's name, version and requirements
│   └── tween.r65
└── easing/
    ├── r65.toml
    └── curves.r65
```

A dependency's name selects the matching package from the root
`[workspace]`, so the directory and the package name should agree.

## Adding a package

1. Create the directory and its `r65.toml`:

   ```toml
   [package]
   name        = "tween"
   version     = "0.1.0"
   r65-version = "0.3"     # the oldest r65c that builds it

   [lib]
   include_dir = "."

   [dependencies]
   easing = { git = "https://github.com/BubbleZapGames/r65-packages", version = "0.1" }
   ```

2. Add the directory to `members` in the root `r65.toml`.
3. Add a row to the table under [Packages](#packages).

`r65pkg check`, run in the package's directory, validates the manifests and
the requirements without compiling anything.

## Releasing

Each package is released by itself, under a `<name>-vX.Y.Z` tag:

1. Bump `version` in the package's `r65.toml` and commit the bump.
2. Run `r65pkg tag tween` to create `tween-v0.2.0` from the committed version.
3. Push the tag with `git push origin tween-v0.2.0`.

The tag must agree with the manifest it points at. If it doesn't, a
resolver refuses it, so tag only through `r65pkg tag`. Follow semver: while
a package is `0.x`, a breaking change bumps the minor version.

## Guidelines for packages

R65 includes source into one flat namespace, so a package's names share space
with every other package in a build.

- **Prefix public names.** A package's names collide with any other
  package's names in the same build. Use names like `tween_start` and
  `TWEEN_SLOTS`, not `start` and `SLOTS`.
- **Every addition can break a user.** A new public function can collide with
  a name a project already uses, so treat additions with care, even in a
  minor release.
- **Include other packages by qualified name**, as in
  `include!("easing/curves.r65")`. A bare `include!("curves.r65")` fails as
  ambiguous once two packages provide that file name.
- **Let the compiler place statics.** Avoid fixed addresses like
  `#[zeropage(0x40)]`: two packages that fix the same address overlap
  without any error.
- **State what you need from the build.** List required cfg conditions
  (`cfg = ["snes"]`) and the minimum compiler (`r65-version`) in `[package]`.
- **Keep files independent.** Users include only the files they need, and
  dead-function elimination removes the functions they don't call. Statics
  are always kept, so keep them few.
