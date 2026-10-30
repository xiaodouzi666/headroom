"""Ephemeral proposal module replacement for focused compatibility tests only."""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import headroom.verify

DIRECTORY = Path(__file__).parent


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    setattr(headroom.verify, name.rsplit(".", 1)[-1], module)


load("headroom.verify.training_coverage", DIRECTORY / "training_coverage.py")
load("headroom.verify.compare", DIRECTORY / "compare.py.txt")
load("headroom.verify.runner", DIRECTORY / "runner.py.txt")
