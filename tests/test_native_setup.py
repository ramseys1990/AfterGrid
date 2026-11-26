import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient
from core import native_setup as native


@pytest.fixture
def upstream(monkeypatch):
    state = {"password": "admin", "registered": False, "calls": [], "failure": None}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, value=None, **headers):
            self.send_response(code)
            for key, val in headers.items():
                self.send_header(key.replace("_", "-"), val)
            self.end_headers()
            if value is not None:
                self.wfile.write(json.dumps(value).encode())

        def handle_request(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = parse_qs(raw.decode()) if self.path == "/login" else json.loads(raw or b"{}")
            state["calls"].append((self.command, self.path))
            if state["failure"] == self.path:
                return self.respond(503, {"detail": "secret native response must never escape"})
            if self.path == "/api/v1/users/register":
                state["registered"] = True
                return self.respond(204)
            if self.path == "/api/v1/users/login":
                return self.respond(200, {"token": "Bearer native-test-token"})
            if self.path == "/api/v1/users/self":
                assert self.headers["Authorization"] == "Bearer native-test-token"
                return self.respond(200, {"item": {"email": "operator@example.test"}})
            if self.path == "/api/v1/users/logout":
                return self.respond(204)
            if self.path == "/login":
                password = base64.b64decode(payload["password_base64"][0]).decode()
                if password != state["password"]:
                    return self.respond(302, Location="/login?invalid=true")
                return self.respond(302, Location="http://" + self.headers["Host"] + "/", Set_Cookie="grocy_session=valid; Path=/")
            if self.path == "/api/user":
                assert "grocy_session=valid" in self.headers.get("Cookie", "")
                return self.respond(200, [{"id": 1, "username": "admin", "first_name": "Existing", "last_name": "Operator"}])
            if self.path == "/api/users/1":
                assert payload["first_name"] == "Existing"
                state["password"] = base64.b64decode(payload["password_base64"]).decode()
                return self.respond(204)
            if self.path == "/logout":
                return self.respond(302, Location="/")
            self.respond(404)

        do_GET = do_POST = do_PUT = handle_request
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for module in native.BASE:
        monkeypatch.setitem(native.BASE, module, "http://127.0.0.1:" + str(server.server_port))
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def payload(module="homebox", mode="create"):
    value = {"mode": mode, "username": "operator@example.test" if module == "homebox" else "admin",
             "password": "long <native> password ü", "confirmed": True}
    if module == "homebox" and mode == "create":
        value["name"] = "Operator"
    return value


def test_homebox_native_registration_login_and_session_cleanup(upstream):
    assert native.prepare("homebox", payload())["ok"]
    assert upstream["registered"]
    assert upstream["calls"] == [("POST", "/api/v1/users/register"), ("POST", "/api/v1/users/login"),
                                 ("GET", "/api/v1/users/self"), ("POST", "/api/v1/users/logout")]


def test_grocy_native_default_change_and_independent_login(upstream):
    assert native.prepare("grocy", payload("grocy", "secure-default"))["ok"]
    assert upstream["password"] == payload()["password"]
    assert ("PUT", "/api/users/1") in upstream["calls"]
    assert upstream["calls"].count(("POST", "/login")) == 3


def test_grocy_verify_never_changes_existing_account(upstream):
    upstream["password"] = payload()["password"]
    assert native.prepare("grocy", payload("grocy", "verify"))["ok"]
    assert all(method != "PUT" for method, path in upstream["calls"])


def test_grocy_default_check_fails_closed_on_native_outage(upstream):
    upstream["password"] = payload()["password"]
    upstream["failure"] = "/login"
    with pytest.raises(native.SetupError) as err:
        native.prepare("grocy", payload("grocy", "verify"))
    assert "secret native response" not in str(err.value)


def test_grocy_unknown_password_is_not_reset(upstream):
    upstream["password"] = "already configured password"
    with pytest.raises(native.NativeAuthError):
        native.prepare("grocy", payload("grocy", "secure-default"))
    assert upstream["password"] == "already configured password"
    assert all(method != "PUT" for method, path in upstream["calls"])


def test_homebox_partial_change_instructs_verify_instead_of_recreate(upstream):
    upstream["failure"] = "/api/v1/users/login"
    with pytest.raises(native.SetupError, match="Verify existing account"):
        native.prepare("homebox", payload())


@pytest.mark.parametrize("change", [{"password": "short"}, {"confirmed": False}, {"url": "http://evil.test"}, {"mode": "reset"}])
def test_invalid_setup_does_not_contact_native_app(upstream, change):
    with pytest.raises(ValueError):
        native.prepare("homebox", {**payload(), **change})
    assert upstream["calls"] == []


def login(client, root):
    (root / "setup-token").write_text("native-test-token")
    assert client.post("/api/setup", json={"username": "admin", "password": "long portal password",
        "token": "native-test-token"}, headers={"Origin": "http://testserver"}).status_code == 201


def test_portal_setup_auth_origin_admission_and_no_secret_echo(tmp_path, monkeypatch):
    from core import app as portal
    calls = []
    def worker(path, *args):
        return (200, []) if path == "/jobs" else (200, [{"id": "homebox", "status": "running", "shared": False}])
    monkeypatch.setattr(portal, "call", worker)
    monkeypatch.setattr(portal, "prepare_native", lambda ident, value: calls.append(ident) or {"ok": True})
    url = "/api/admin/modules/homebox/native-setup"
    with TestClient(portal.create_app(tmp_path)) as client:
        assert client.post(url, json=payload(), headers={"Origin": "http://testserver"}).status_code == 401
        login(client, tmp_path)
        assert client.post(url, json=payload()).status_code == 403
        bad = client.post(url, json={**payload(), "password": ["secret-input"]}, headers={"Origin": "http://testserver"})
        assert bad.status_code == 400 and "secret-input" not in bad.text
        assert client.post(url, json=payload(), headers={"Origin": "http://testserver"}).status_code == 200
        assert calls == ["homebox"]
        assert client.get("/native-setup/homebox").status_code == 200


@pytest.mark.parametrize("mode", ["AFTERGRID_RECOVERY_CORE_ONLY", "AFTERGRID_RECOVERY_OFFLINE"])
def test_recovery_refuses_native_setup(tmp_path, monkeypatch, mode):
    from core import app as portal
    with TestClient(portal.create_app(tmp_path)) as client:
        login(client, tmp_path)
    monkeypatch.setenv(mode, "1")
    monkeypatch.setattr(portal, "prepare_native", lambda *args: pytest.fail("Must not contact native service"))
    with TestClient(portal.create_app(tmp_path)) as client:
        assert client.post("/api/login", json={"username": "admin", "password": "long portal password"},
                           headers={"Origin": "http://testserver"}).status_code == 200
        assert client.get("/native-setup/grocy").status_code == 409
        assert client.post("/api/admin/modules/grocy/native-setup", json=payload("grocy", "verify"),
                           headers={"Origin": "http://testserver"}).status_code == 409


def test_portal_refuses_shared_or_busy_module(tmp_path, monkeypatch):
    from core import app as portal
    monkeypatch.setattr(portal, "call", lambda path: (200, []) if path == "/jobs" else
                        (200, [{"id": "homebox", "status": "running", "shared": True}]))
    monkeypatch.setattr(portal, "prepare_native", lambda *args: pytest.fail("Must not contact shared service"))
    with TestClient(portal.create_app(tmp_path)) as client:
        login(client, tmp_path)
        assert client.post("/api/admin/modules/homebox/native-setup", json=payload(),
                           headers={"Origin": "http://testserver"}).status_code == 409
