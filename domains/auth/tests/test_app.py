import importlib
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from domains.auth.services.key_manager import KeyManager

SERVICE_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
for path in (SERVICE_ROOT, DOMAIN_ROOT, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.append(str(path))


def load_fastapi_app() -> FastAPI:
    last_exc: ModuleNotFoundError | None = None
    for module_name in ("domains.auth.main", "auth.app", "auth.main", "main"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            last_exc = exc
            continue
        app = getattr(module, "app", None)
        if isinstance(app, FastAPI):
            return app
    message = "FastAPI application instance not found"
    if last_exc:
        raise AssertionError(message) from last_exc
    raise AssertionError(message)


def test_fastapi_app_instantiates():
    app = load_fastapi_app()
    assert isinstance(app, FastAPI)


def test_jwks_endpoint():
    app = load_fastapi_app()
    # 키가 없으면 생성
    KeyManager.ensure_keys()
    with TestClient(app) as client:
        resp = client.get("/api/v1/auth/.well-known/jwks.json")
        assert resp.status_code == 200
        data = resp.json()
        assert "keys" in data
        assert isinstance(data["keys"], list)
