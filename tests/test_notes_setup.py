import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

from core import native_setup as native


TOKEN = "a" * 32


def login_form(token=""):
    return '<form id="dw__login"><input name="sectok" value="'+token+'"><input name="u"><input name="p" type="password"></form>'


@pytest.fixture
def notes(monkeypatch):
    state = {"configured": False, "password": None, "calls": [], "admin": True,
             "closed": True, "acl": True, "registration_disabled": True,
             "updatecheck": True, "save": True, "failure": None, "guest_blocked": True,
             "login_token": "", "config_token": TOKEN, "redirect_path": "/start"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, html="", code=200, **headers):
            self.send_response(code)
            for key, val in headers.items():
                self.send_header(key.replace("_", "-"), val)
            self.end_headers()
            self.wfile.write(html.encode())

        def handle_request(self):
            data = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode(), keep_blank_values=True)
            state["calls"].append((self.command, self.path))
            if state["failure"] == self.path:
                return self.respond("secret native diagnostics", code=503)
            cookie = self.headers.get("Cookie", "")
            authenticated = "wiki_session=admin" in cookie
            if self.path == "/install.php":
                if self.command == "GET":
                    if state["configured"]:
                        return self.respond("Already configured")
                    return self.respond('<form><input name="d[title]"><input name="d[superuser]"><input name="d[password]" type="password"><input name="d[acl]" type="checkbox"><input name="d[license]" value="0" type="radio"></form>')
                assert not state["configured"]
                assert data["d[acl]"] == ["1"] and data["d[policy]"] == ["2"]
                assert "d[allowreg]" not in data and "d[pop]" not in data
                assert data["d[license]"] == ["0"] and data["d[confirm]"] == data["d[password]"]
                state["password"] = data["d[password]"][0]
                state["configured"] = True
                return self.respond("Installed")
            if self.path == "/doku.php?do=login":
                return self.respond(login_form(state["login_token"]), Set_Cookie="wiki_session=anonymous; Path=/")
            if self.path == "/doku.php" and data.get("do") == ["login"]:
                assert "wiki_session=anonymous" in cookie and data["sectok"] == [state["login_token"]]
                if data["p"] != [state["password"]]:
                    return self.respond(login_form())
                return self.respond(code=302, Location=state["redirect_path"], Set_Cookie="wiki_session=admin; Path=/")
            logout = '<a href="/doku.php?do=logout&amp;sectok='+TOKEN+'">Log out</a>'
            if self.path == "/doku.php?do=admin&page=acl":
                if not authenticated or not state["admin"]:
                    return self.respond(login_form())
                permission = "0" if state["closed"] else "1"
                return self.respond(logout+'<div id="acl__tree"></div><div id="acl__detail"></div><input name="acl[*][@ALL]" value="'+permission+'" type="radio" checked>')
            if self.path == "/doku.php?do=admin&page=config":
                assert authenticated
                checked = lambda flag: " checked" if flag else ""
                html = logout+'<div id="config__manager"><form id="dw__configform">'
                for key, val in {"sectok": state["config_token"], "do": "admin", "page": "config", "save": "1", "config[title]": "Original native title"}.items():
                    html += '<input name="'+key+'" value="'+val+'">'
                html += '<input type="checkbox" name="config[useacl]" value="1"'+checked(state["acl"])+ '>'
                html += '<input type="checkbox" name="config[disableactions][]" value="register"'+checked(state["registration_disabled"])+ '>'
                html += '<input type="checkbox" name="config[updatecheck]" value="1"'+checked(state["updatecheck"])+ '>'
                html += '<select name="config[template]"><option value="dokuwiki" selected>Native</option><option value="other">Other</option></select>'
                html += '<textarea name="config[tagline]">Keep &amp; preserve</textarea></form></div>'
                return self.respond(html)
            if self.path == "/doku.php" and data.get("page") == ["config"]:
                assert authenticated and data["sectok"] == [TOKEN] and data["save"] == ["1"]
                assert data["config[title]"] == ["Original native title"] and data["config[template]"] == ["dokuwiki"]
                assert data["config[tagline]"] == ["Keep & preserve"]
                if state["save"]:
                    state["updatecheck"] = data["config[updatecheck]"] != ["0"]
                return self.respond(code=302, Location=state["redirect_path"])
            if self.path == "/doku.php?id=aftergrid:access-check":
                assert not authenticated
                return self.respond(login_form() if state["guest_blocked"] else "Public wiki page")
            if self.path == "/doku.php" and data.get("do") == ["logout"]:
                assert authenticated and data["sectok"] == [TOKEN]
                return self.respond(code=302, Location=state["redirect_path"], Set_Cookie="wiki_session=; Max-Age=0; Path=/")
            return self.respond(code=404)

        do_GET = do_POST = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setitem(native.BASE, "notes", "http://127.0.0.1:" + str(server.server_port))
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def value(mode="create"):
    return {"mode": mode, "username": "operator", "password": "disposable-notes-password", "confirmed": True}


@pytest.mark.parametrize("redirect_path", ["/start", "/doku.php?id=start"])
def test_native_installer_login_closed_policy_config_preservation_and_logout(notes, redirect_path):
    notes["redirect_path"] = redirect_path
    result = native.prepare("notes", value())
    assert result["ok"] and notes["configured"] and notes["updatecheck"] is False
    assert value()["password"] not in json.dumps(result)
    assert notes["calls"][-1] == ("POST", "/doku.php")


@pytest.mark.parametrize("redirect_path", ["http://untrusted.invalid/start", "/unexpected"])
def test_unreviewed_redirects_are_refused_without_following(notes, redirect_path):
    notes["redirect_path"] = redirect_path
    with pytest.raises(native.SetupError, match="redirect refused"):
        native.prepare("notes", value())
    assert not any(path == "/unexpected" for method, path in notes["calls"])


def test_existing_verify_never_reconfigures_or_resets(notes):
    native.prepare("notes", value())
    notes["calls"].clear()
    assert native.prepare("notes", value("verify"))["ok"]
    assert ("POST", "/install.php") not in notes["calls"]
    assert notes["calls"].count(("POST", "/doku.php")) == 2  # login, logout
    with pytest.raises(native.SetupError, match="already configured"):
        native.prepare("notes", value())


def test_unknown_password_and_non_admin_are_refused_without_reset(notes):
    native.prepare("notes", value())
    notes["password"] = "different existing password"
    with pytest.raises(native.NativeAuthError):
        native.prepare("notes", value("verify"))
    assert notes["password"] == "different existing password"
    notes["password"] = value()["password"]
    notes["admin"] = False
    with pytest.raises(native.NativeAuthError):
        native.prepare("notes", value("verify"))


@pytest.mark.parametrize("setting", ["closed", "acl", "registration_disabled", "updatecheck"])
def test_existing_native_policy_must_be_verified_without_changing_it(notes, setting):
    native.prepare("notes", value())
    notes[setting] = setting == "updatecheck"
    notes["calls"].clear()
    with pytest.raises(native.SetupError):
        native.prepare("notes", value("verify"))
    assert notes["calls"].count(("POST", "/doku.php")) == 2


def test_native_config_readback_failure_keeps_setup_unsuccessful(notes):
    notes["save"] = False
    with pytest.raises(native.SetupError, match="online update"):
        native.prepare("notes", value())


def test_native_errors_are_not_echoed(notes):
    notes["failure"] = "/install.php"
    with pytest.raises(native.SetupError) as err:
        native.prepare("notes", value())
    assert "secret native diagnostics" not in str(err.value)


def test_notes_username_is_bounded_before_native_requests(notes):
    with pytest.raises(ValueError):
        native.prepare("notes", {**value(), "username": "Admin:invalid"})
    assert notes["calls"] == []


def test_independent_guest_check_must_refuse_access(notes):
    native.prepare("notes", value())
    notes["guest_blocked"] = False
    with pytest.raises(native.SetupError, match="Anonymous"):
        native.prepare("notes", value("verify"))


def test_nonempty_native_login_token_is_preserved(notes):
    notes["login_token"] = TOKEN
    assert native.prepare("notes", value())["ok"]


def test_empty_or_invalid_authenticated_token_never_submits_config(notes):
    notes["config_token"] = ""
    with pytest.raises(native.SetupError, match="authenticated configuration token"):
        native.prepare("notes", value())
    # Only login and best-effort logout may post to the native wiki.
    assert notes["calls"].count(("POST", "/doku.php")) == 2
