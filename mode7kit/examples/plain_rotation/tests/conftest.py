import sys
from pathlib import Path

import pytest
from mesen_gdb.rom_driver import Rom
from mesen_gdb.rom_driver.pytest_plugin import snes, state   # noqa: F401

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(scope="session")
def rom():
    return Rom(Path(__file__).parent.parent / "build" / "PLAINROT.smc")
