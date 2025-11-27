import importlib
import sys
from pathlib import Path

from fastapi import FastAPI

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


def load_fastapi_app() -> FastAPI:
    for module_name in ("domains.my.main", "main"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        app = getattr(module, "app", None)
        if isinstance(app, FastAPI):
            return app
    raise AssertionError("FastAPI application instance not found")


def test_fastapi_app_instantiates():
    app = load_fastapi_app()
    assert isinstance(app, FastAPI)
