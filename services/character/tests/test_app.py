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
    last_exc: ModuleNotFoundError | None = None
    for module_name in ("app.main", "main"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            last_exc = exc
            continue
        app = getattr(module, "app", None)
        if isinstance(app, FastAPI):
            return app
    message = "FastAPI application instance not found"
    if last_exc is not None:
        raise AssertionError(message) from last_exc
    raise AssertionError(message)


def test_fastapi_app_instantiates():
    app = load_fastapi_app()
    assert isinstance(app, FastAPI)
