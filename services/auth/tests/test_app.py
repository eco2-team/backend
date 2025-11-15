import importlib

from fastapi import FastAPI


def load_fastapi_app() -> FastAPI:
    for module_name in ("app.main", "main"):
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
