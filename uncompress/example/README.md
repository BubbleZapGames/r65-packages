# uncompress example

A ROM that decodes one sample in every format `r65x packer` writes, and
checks each result against the original.

`make` writes the sample (`assets/make_sample.py`), packs it with `r65x packer pack -f`
into `build/sample.<format>`, and builds the ROM. The ROM decodes each
format into `OUT`. Each format's result goes in `RESULTS[i]`: 1 if the bytes match the
original and the 16 bytes after them are untouched, 2 if not. The size the
decoder returned goes in `SIZES[i]`. `DONE` is set to 1 at the end.

`make tests` runs `tests/test_uncompress.py`, which reads those values
through `mesen_gdb.rom_driver` (`pip install -e Mesen-GDB/python` in the R65
repo).
