from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def scratch():
    with TemporaryDirectory(prefix="synapse-persistence-") as directory:
        yield Path(directory)
