# uncompress

Decoders for every format `r65x packer` writes, for
[R65](https://github.com/BubbleZapGames/R65) on the SNES. Pack an asset at
build time and put it in ROM. At run time, decode it into RAM, then DMA it to
VRAM or use it in place.

Each format has its own file. Include only the ones a game uses. A decoder
the game never calls is dropped at compile time. The package allocates no
memory: a decoder keeps its state on the stack while it runs.

## Quick start

```toml
# r65.toml
[dependencies]
uncompress = { git = "https://github.com/BubbleZapGames/r65-packages", version = "0.1" }
```

```bash
r65x packer pack assets/title.chr -o assets/title.lz5 -x lz5 -f
```

```rust
include!("stdlib/sneslib.r65")
include!("uncompress/lz5.r65")

static TITLE_LZ5 = include_bytes!("../assets/title.lz5");

#[ram]
static mut TILES: [u8; 8192];

fn load_title() {
    let n: u16 = lz5_uncompress(&TITLE_LZ5 as far *u8, &TILES as far *u8);
    dma_copy_vram(0, &TILES as far *u8, 0x0000, n);
}
```

Pass `-f` to the packer: without it, an existing output file's size is
kept, and the data is truncated or padded to fit.

## Formats

| File | Function | Sample size | Cycles per byte |
|---|---|---|---|
| `aplib.r65` | `aplib_uncompress(src, dst) -> u16` | 1575 | 108 |
| `byte_rle.r65` | `byte_rle_uncompress(src, dst) -> u16` | 3262 | 67 |
| `rle1.r65` | `rle1_uncompress(src, dst) -> u16` | 3558 | 41 |
| `rle2.r65` | `rle2_uncompress(src, dst, size)` | 3368 | 79 |
| `lz1.r65` | `lz1_uncompress(src, dst) -> u16` | 1308 | 44 |
| `lz2.r65` | `lz2_uncompress(src, dst) -> u16` | 1308 | 44 |
| `lz3.r65` | `lz3_uncompress(src, dst) -> u16` | 1328 | 50 |
| `lz4.r65` | `lz4_uncompress(src, dst, size) -> u16` | 1603 | 45 |
| `lz5.r65` | `lz5_uncompress(src, dst) -> u16` | 1151 | 44 |
| `lz19.r65` | `lz19_uncompress(src, dst) -> u16` | 1150 | 51 |
| `lz77.r65` | `lz77_uncompress(src, dst, size) -> u16` | 1761 | 87 |
| `hal.r65` | `hal_uncompress(src, dst) -> u16` | 1597 | 42 |

`src` and `dst` are `far *u8`. Each function returns the number of bytes it
wrote. The sizes and speeds are from the example's 3575-byte sample (text,
runs, tilemap-like rows, mirrored and inverted copies, noise): the size is
the packed size in bytes, and the speed is CPU cycles per output byte, measured in Mesen, at
`-O1` with the Default ABI. Every file opens with a description of its format.

- **lz5 and lz19** pack smallest here. **hal** and the **lz1/lz2** family
  decode fastest. All the LZ formats share one command layout (see `lz1.r65`)
  and differ in the copy commands.
- **aplib** suits text and mixed data best. It is the slowest, because it reads its
  commands a bit at a time.
- **rle1** decodes fastest, but packs only runs.
- **lz4**, **lz77** and **rle2** have no end marker. lz4 and lz77 take the
  packed `size` (`ARRAY.len()` of the `include_bytes!` static). rle2 takes
  the unpacked size.
- **byte_rle** needs a byte value the data never holds, and runs of at most
  256 bytes: the packer fails on other data.

## Rules

- **`dst` must be RAM.** Runs and back-references read back what was written.
  To fill VRAM, decode to WRAM and DMA it.
- **Neither the packed data nor the output may cross a 64KB bank boundary.**
  The decoders step their pointers within the bank. A LoROM asset is in one
  bank anyway. In WRAM, keep the buffer within `$7E` or within `$7F`.
- **The data is not checked.** A corrupt or wrongly packed stream writes past
  the buffer.
- Each decoder reads its arguments from the stack. Under the FixedStack ABI,
  the game includes `stdlib/scratch_regs.r65`, as `r65x init` sets up.

## Example

`example/` decodes the sample in all twelve formats and checks each result
against the original: `make` builds the ROM (it packs the sample with `r65x
packer`), `make tests` runs the check in Mesen-GDB.
