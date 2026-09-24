import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from uds_assistant.config import Settings
from uds_assistant.generator.suites import build_suite
from uds_assistant.store import ProjectStore


def test_four_eyes_blocks_self_approval(profile):
    d = Path(tempfile.mkdtemp())
    ps = ProjectStore(Settings(data_dir=d))
    ps.create("demo")
    ps.set_profile("demo", profile, "test", "alice", "engineer")
    tests = build_suite(profile)[:1]
    tests[0].created_by = "alice"
    ps.save_tests("demo", tests, "alice", "engineer", "generated")
    with pytest.raises(PermissionError):
        ps.review_test("demo", tests[0].id, "alice", "lead", "approved", "", four_eyes=True)
    ps.review_test("demo", tests[0].id, "bob", "lead", "approved", "", four_eyes=True)
    assert ps.get_test("demo", tests[0].id).status == "approved"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("UDS_DATA_DIR", str(tmp_path))
    import importlib

    import uds_assistant.api.app as app_module
    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_api_end_to_end_workflow(client):
    H = {"X-User": "alice", "X-Role": "engineer"}
    HL = {"X-User": "bob", "X-Role": "lead"}
    assert client.get("/health").status_code == 200
    assert client.post("/projects", json={"name": "demo"}, headers=H).status_code == 201
    with open("data/samples/bcm_ecu_profile.yaml", "rb") as f:
        r = client.post("/projects/demo/profile", files={"file": ("bcm.yaml", f, "text/yaml")}, headers=H)
    assert r.status_code == 200
    r = client.post("/projects/demo/generate", json={}, headers=H)
    assert r.status_code == 200 and r.json()["coverage"]["percent"] == 100.0
    tests = client.get("/projects/demo/tests", headers=H).json()["tests"]
    r = client.post("/projects/demo/run", json={"target": "simulator"}, headers=H)
    assert r.status_code == 400  # nothing approved yet
    for t in tests:
        client.post(f"/projects/demo/tests/{t['id']}/review", json={"decision": "approved"}, headers=HL)
    r = client.post("/projects/demo/run", json={"target": "simulator"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] == body["total"]
    r = client.post("/projects/demo/run", json={"target": "hardware", "hw_interface": "can0"}, headers=H)
    assert r.status_code == 403
