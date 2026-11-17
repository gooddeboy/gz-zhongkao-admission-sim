import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.generator import load_fixture  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def small_dataset():
    return load_fixture("small_main")


@pytest.fixture()
def client(tmp_path):
    app = create_app(db_path=tmp_path / "test.db", snapshot_dir=tmp_path / "snapshots")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def small_client(client):
    res = client.post("/api/dataset/generate", json={"preset": "small", "confirm_reset": True})
    assert res.status_code == 200, res.text
    return client


@pytest.fixture()
def completed_run(small_client):
    res = small_client.post(
        "/api/runs",
        json={"g1": 720, "delta": 40, "city_line": 600, "trace_level": "full", "note": "pytest"},
    )
    assert res.status_code == 200, res.text
    run = res.json()
    res = small_client.post(f"/api/runs/{run['id']}/execute-all")
    assert res.status_code == 200, res.text
    return run["id"]
