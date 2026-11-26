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
    state = {"password": "admin", "registered": False, "calls": [], "failure": None,
             "media_password": None, "media_username": "unclaimed", "media_complete": False,
             "media_remote": True, "media_admin": True}
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
            if self.path == "/System/Info/Public":
                return self.respond(200, {"StartupWizardCompleted": state["media_complete"]})
            if self.path == "/Users/Public":
                return self.respond(200, [{"Name": state["media_username"], "HasPassword": state["media_password"] is not None,
                                          "HasConfiguredPassword": state["media_password"] is not None}])
            if self.path == "/Startup/User":
                if self.command == "GET":
                    return self.respond(200, {"Name": state["media_username"]})
                assert state["media_password"] is None
                state["media_username"], state["media_password"] = payload["Name"], payload["Password"]
                return self.respond(204)
            if self.path == "/Users/AuthenticateByName":
                if payload["Username"] != state["media_username"] or payload["Pw"] != state["media_password"]:
                    return self.respond(401)
                return self.respond(200, {"AccessToken": "disposable-native-media-token"})
            if self.path in {"/Users/Me", "/Startup/RemoteAccess", "/Startup/Complete", "/System/Configuration/network", "/Sessions/Logout"}:
                assert 'Token="disposable-native-media-token"' in self.headers.get("Authorization", "")
                if self.path == "/Users/Me":
                    return self.respond(200, {"Name": state["media_username"], "HasPassword": state["media_password"] is not None,
                                              "Policy": {"IsAdministrator": state["media_admin"]}})
                if self.path == "/System/Configuration/network":
                    return self.respond(200, {"EnableRemoteAccess": state["media_remote"]})
                if self.path == "/Startup/RemoteAccess":
                    state["media_remote"] = payload["EnableRemoteAccess"]
                if self.path == "/Startup/Complete":
                    state["media_complete"] = True
                return self.respond(204)
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
                return self.respond(302, Location="http://127.0.0.1:" + str(server.server_port) + "/", Set_Cookie="grocy_session=valid; Path=/")
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
             "password": "long <native> password �", "confirmed": True}
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


def test_media_create_finishes_wizard_checks_admin_remote_access_and_logs_out(upstream):
    assert native.prepare("media", payload("media"))["ok"]
    assert upstream["media_complete"] and upstream["media_remote"] is False
    assert upstream["media_password"] == payload()["password"]
    assert upstream["calls"][-1] == ("POST", "/Sessions/Logout")


def test_media_partial_setup_can_finish_without_resetting_password(upstream):
    upstream["failure"] = "/Startup/RemoteAccess"
    with pytest.raises(native.SetupError):
        native.prepare("media", payload("media"))
    assert upstream["media_password"] == payload()["password"] and not upstream["media_complete"]
    upstream["calls"].clear()
    with pytest.raises(native.SetupError, match="existing credentials"):
        native.prepare("media", payload("media"))
    assert ("POST", "/Startup/User") not in upstream["calls"]
    upstream["failure"] = None
    assert native.prepare("media", payload("media", "finish-setup"))["ok"]
    assert ("POST", "/Startup/User") not in upstream["calls"]


def test_media_existing_setup_verify_does_not_change_configuration(upstream):
    native.prepare("media", payload("media"))
    upstream["calls"].clear()
    assert native.prepare("media", payload("media", "verify"))["ok"]
    assert all(path in {"/Users/AuthenticateByName", "/Sessions/Logout"}
               for method, path in upstream["calls"] if method != "GET")
    upstream["calls"].clear()
    with pytest.raises(native.SetupError, match="already configured"):
        native.prepare("media", payload("media"))
    assert upstream["calls"] == [("GET", "/System/Info/Public")]


def test_media_refuses_non_admin_and_does_not_echo_native_error(upstream):
    upstream["media_password"] = payload()["password"]
    upstream["media_username"] = "admin"
    upstream["media_admin"] = False
    with pytest.raises(native.SetupError, match="administrator"):
        native.prepare("media", payload("media", "finish-setup"))
    assert ("POST", "/Startup/Complete") not in upstream["calls"]
    upstream["failure"] = "/Users/AuthenticateByName"
    with pytest.raises(native.SetupError) as error:
        native.prepare("media", payload("media", "verify"))
    assert "secret native response" not in str(error.value)


@pytest.mark.parametrize("change", [{"password": "short"}, {"confirmed": False}, {"url": "http://evil.test"}, {"mode": "reset"}])
def test_invalid_setup_does_not_contact_native_app(upstream, change):
    with pytest.raises(ValueError):
        native.prepare("homebox", {**payload(), **change})
    assert upstream["calls"] == []


def login(client, root):
    (root / "setup-token").write_text("native-test-token")
    assert client.post("/api/setup", json={"username": "admin", "password": "long portal password",
        "token": "native-test-token"}, headers={"Origin": "http://testserver"}).status_code == 201


@pytest.mark.parametrize("ident", ["homebox", "media"])
def test_portal_setup_auth_origin_admission_and_no_secret_echo(tmp_path, monkeypatch, ident):
    from core import app as portal
    calls = []
    def worker(path, *args):
        return (200, []) if path == "/jobs" else (200, [{"id": ident, "status": "running", "shared": False}])
    monkeypatch.setattr(portal, "call", worker)
    monkeypatch.setattr(portal, "prepare_native", lambda ident, value: calls.append(ident) or {"ok": True})
    url = "/api/admin/modules/"+ident+"/native-setup"
    value = payload(ident)
    with TestClient(portal.create_app(tmp_path)) as client:
        assert client.post(url, json=value, headers={"Origin": "http://testserver"}).status_code == 401
        login(client, tmp_path)
        assert client.post(url, json=value).status_code == 403
        bad = client.post(url, json={**value, "password": ["secret-input"]}, headers={"Origin": "http://testserver"})
        assert bad.status_code == 400 and "secret-input" not in bad.text
        assert client.post(url, json=value, headers={"Origin": "http://testserver"}).status_code == 200
        assert calls == [ident]
        assert client.get("/native-setup/"+ident).status_code == 200


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

