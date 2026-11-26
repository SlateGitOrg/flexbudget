from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from flexbudget.engine import run_engine
from flexbudget.generate import Dataset, generate, write_dataset
from flexbudget.inputs import Inputs, load_inputs

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return generate(7)


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory, dataset) -> Path:
    path = tmp_path_factory.mktemp("data")
    write_dataset(dataset, path)
    return path


@pytest.fixture(scope="session")
def inputs(data_dir) -> Inputs:
    return load_inputs(data_dir)


@pytest.fixture(scope="session")
def variance(inputs):
    return run_engine(inputs)


@pytest.fixture()
def project_copy(tmp_path) -> Path:
    """A throwaway copy of the shipped Power BI project that a test may break."""
    target = tmp_path / "powerbi"
    shutil.copytree(REPO / "powerbi", target)
    return target
