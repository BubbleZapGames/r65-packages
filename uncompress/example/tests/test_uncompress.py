"""Every decoder, run by the example ROM on the sample packed by r65x packer.

The ROM checks each result itself (src/main.r65): the bytes match the
original and the 16 after them are untouched. The test reads those verdicts,
the sizes the decoders returned, and the last output against the sample.
"""
from pathlib import Path

import pytest

FORMATS = ["aplib", "byte_rle", "rle1", "rle2", "lz1", "lz2", "lz3", "lz4",
           "lz5", "lz19", "lz77", "hal"]
SAMPLE = (Path(__file__).parent.parent / "build" / "sample.bin").read_bytes()


@pytest.fixture(scope="module")
def run(rom):
    with rom.session() as s:
        s.wait(300)
        assert s.var.DONE == 1, "the ROM did not finish decoding"
        sizes = s.raw("SIZES").bytes()
        yield {
            "results": list(s.raw("RESULTS").bytes()),
            "sizes": [sizes[i] | sizes[i + 1] << 8 for i in range(0, 2 * len(FORMATS), 2)],
            "out": s.raw("OUT").bytes()[:len(SAMPLE)],
        }


@pytest.mark.parametrize("i,fmt", list(enumerate(FORMATS)))
def test_decodes_to_the_original(run, i, fmt):
    assert run["results"][i] == 1, f"{fmt}: output differs, or ran past the end"
    assert run["sizes"][i] == len(SAMPLE), f"{fmt}: returned the wrong size"


def test_last_output_is_the_sample(run):
    assert bytes(run["out"]) == SAMPLE
