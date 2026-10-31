"""Write the sample the example ROM decodes: a few KB that exercise every
command of every format - text, long and short runs, word runs, rising
bytes, tile-like data, mirrored and bit-reversed copies, noise.

It never holds the byte $FE, so byte_rle has a free tag, and no run is
longer than 256 bytes, the longest byte_rle can write. The length is odd,
so rle2's planes differ in size.

    python make_sample.py out.bin
"""
import random
import sys


def rev(b):
    return int(f"{b:08b}"[::-1], 2)


def sample():
    rnd = random.Random(65816)
    no_fe = [v for v in range(256) if v != 0xFE]
    out = bytearray()
    out += (b"The quick brown fox jumps over the lazy dog. " * 12)[:500]
    out += bytes(250)
    out += bytes(0xFF for _ in range(40))
    out += bytes([0x12, 0x34]) * 60
    out += bytes(i for i in range(200))
    for i in range(48):                      # tilemap-ish rows
        out += bytes([i, 0x20]) * rnd.randrange(1, 9)
        out += bytes(rnd.choice([0, 1, 2, 0x55]) for _ in range(rnd.randrange(0, 12)))
    tile = bytes(rnd.choice(no_fe) for _ in range(64))
    out += tile
    out += bytes(rev(b) for b in tile if rev(b) != 0xFE)   # bit-reversed copy
    out += tile[::-1]                                     # mirrored copy
    out += bytes(b ^ 0xFF for b in tile if b != 0x01)       # inverted copy
    out += bytes(rnd.choice(no_fe) for _ in range(300))    # noise
    out += b"abcdefgh" * 40
    out += bytes(range(0, 0xFE)) * 2                       # long rising runs
    out += bytes(rnd.choice(b"ab\x00") for _ in range(400))
    if len(out) % 2 == 0:
        out.append(0x42)
    assert 0xFE not in out
    return bytes(out)


if __name__ == "__main__":
    with open(sys.argv[1], "wb") as f:
        f.write(sample())
