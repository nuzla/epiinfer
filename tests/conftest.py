import json
from pathlib import Path

import pytest

import epiinfer
from epiinfer import load_dataset

DEMO = Path(epiinfer.__file__).parent / "demo_data"


@pytest.fixture(scope="session")
def demo_path():
    return DEMO


@pytest.fixture(scope="session")
def data():
    return load_dataset(DEMO)


@pytest.fixture(scope="session")
def golden():
    return json.loads((Path(__file__).parent / "golden_original_scripts.json").read_text())
