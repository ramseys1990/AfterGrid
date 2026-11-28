"""Browser admission and ambiguous dispatch must preserve the update hold."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from core import app as core_app

ORIGIN = {"Origin": "http://testserver"}
COMMIT = "a" * 40
DIGEST = "b" * 64


@pytest.fixture
def portal(tmp_path, monkeypatch):
    inventory = {"manifest_job": 5, "records": [
        {"key": key, "aftergrid_pinned": True, "verification": "isolated",
         "repository_status": "present"} for key in ("core", "worker")]}
    checksum = hashlib.sha256(json.dumps(
        inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ready = {"activation_enabled": True, "candidate": {"candidate_sha256": DIGEST},
             "prepare_state": "finished"}
    calls = []
    dispatch = {"code": 202}
    marker = tmp_path / "recovery-maintenance.json"

    def call(path, payload=None):
        calls.append((path, payload))
        if path == "/jobs":
            return 200, [{"id": 5, "state": "succeeded"}]
        if path == "/recovery-manifest":
            return 200, inventory
        if path == "/core-update/status":
            return 200, ready
        if path == "/core-update/prepare":
            return 202, {"accepted": True}
        if path == "/core-update/apply":
            # The claim must already be durable before a worker starts.
            assert json.loads(marker.read_text())["phase"] == "updating"
            return dispatch["code"], {"accepted": dispatch["code"] == 202}
        raise AssertionError(path)

    monkeypatch.setattr(core_app, "call", call)
    (tmp_path / "setup-token").write_text("test-token")
    with TestClient(core_app.create_app(tmp_path)) as client:
        yield client, calls, ready, dispatch, marker, checksum


def sign_in(client):
    assert client.post("/api/setup", headers=ORIGIN, json={
        "username": "admin", "password": "long test password",
        "token": "test-token"}).status_code == 201


def seal(marker, checksum):
    marker.write_text(json.dumps({"format": 1, "phase": "sealed", "modules": [],
                                 "manifest_job": 5, "inventory_sha256": checksum}))


def test_prepare_requires_admin_origin_and_confirmation(portal):
    client, calls, _, _, _, _ = portal
    path = "/api/admin/core-update/prepare"
    body = {"commit": COMMIT, "confirmed": True}
    assert client.post(path, json=body, headers=ORIGIN).status_code == 401
    sign_in(client)
    assert client.post(path, json=body).status_code == 403
    assert client.post(path, json=body, headers={"Origin": "http://other.invalid"}).status_code == 403
    assert client.post(path, json={**body, "confirmed": False}, headers=ORIGIN).status_code == 409
    assert not any(p == "/core-update/prepare" for p, _ in calls)
    assert client.post(path, json=body, headers=ORIGIN).status_code == 202
    assert calls[-1] == ("/core-update/prepare", {"commit": COMMIT})


@pytest.mark.parametrize("change", [
    {"activation_enabled": False}, {"candidate": {"candidate_sha256": "c" * 64}},
    {"prepare_state": "running"}, {"apply_state": "running"}, {"outcome": "promoted"}])
def test_apply_refuses_unready_or_changed_candidate_without_claim(portal, change):
    client, calls, ready, _, marker, checksum = portal
    sign_in(client)
    seal(marker, checksum)
    before = marker.read_bytes()
    ready.update(change)
    body = {"confirmed": True, "candidate_sha256": DIGEST, "inventory_sha256": checksum}
    assert client.post("/api/admin/core-update/apply", json=body, headers=ORIGIN).status_code == 409
    assert marker.read_bytes() == before
    assert not any(p == "/core-update/apply" for p, _ in calls)


@pytest.mark.parametrize("dispatch_code", [202, 409])
def test_apply_claim_survives_reconnection_and_failed_dispatch(portal, dispatch_code):
    client, calls, _, dispatch, marker, checksum = portal
    sign_in(client)
    seal(marker, checksum)
    body = {"confirmed": True, "candidate_sha256": DIGEST, "inventory_sha256": checksum}
    path = "/api/admin/core-update/apply"
    assert client.post(path, json=body).status_code == 403
    assert json.loads(marker.read_text())["phase"] == "sealed"
    dispatch["code"] = dispatch_code
    assert client.post(path, json=body, headers=ORIGIN).status_code == dispatch_code
    assert json.loads(marker.read_text())["candidate_sha256"] == DIGEST
    cookies = dict(client.cookies)
    with TestClient(core_app.create_app(marker.parent)) as reconnected:
        reconnected.cookies.update(cookies)
        assert reconnected.get("/api/admin/recovery-maintenance").json()["phase"] == "updating"
        assert reconnected.post("/api/admin/recovery-maintenance/release", json={
            "confirmed": True}, headers=ORIGIN).status_code == 409
    assert calls.count(("/core-update/apply", {"candidate_sha256": DIGEST})) == 1
