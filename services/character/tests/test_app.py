import importlib
import sys
from pathlib import Path

from fastapi import FastAPI

CHARACTER_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = Path(__file__).resolve().parents[3]
for path in (CHARACTER_ROOT, SERVICES_ROOT):
    if str(path) not in sys.path:
        sys.path.append(str(path))


def load_fastapi_app() -> FastAPI:
    try:
        module = importlib.import_module("app.main")
    except ModuleNotFoundError as exc:
        raise AssertionError("FastAPI application module not found") from exc
        app = getattr(module, "app", None)
        if isinstance(app, FastAPI):
            return app
    raise AssertionError("FastAPI application instance not found")


def test_fastapi_app_instantiates():
    app = load_fastapi_app()
    assert isinstance(app, FastAPI)
