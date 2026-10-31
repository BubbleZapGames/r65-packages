import pytest
from pathlib import Path
from mesen_gdb.rom_driver import Rom
from mesen_gdb.rom_driver.pytest_plugin import snes, state   # noqa: F401


@pytest.fixture(scope="session")
def rom():
    return Rom(Path(__file__).parent.parent / "build" / "UNCOMPRESS.smc")
