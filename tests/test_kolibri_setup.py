"""Exercise native HTTP/session boundaries, not just helper return values."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from core import native_setup as native


@pytest.fixture
def kolibri(monkeypatch):
    state = {"facilities": [], "jobs": [], "calls": [], "password": None,
             "admin": True, "guest": True, "signup": False, "blank": False,
             "cleanup": True, "task_status": "COMPLETED"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, code=200, cookie=None):
            self.send_response(code)
            if cookie:
                self.send_header("Set-Cookie", cookie + "; Path=/")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def handle_request(self):
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            state["calls"].append((self.command, self.path))
            if self.path == "/api/auth/session/current/" and self.command == "PUT":
                return self.respond({"kind": ["anonymous"]}, cookie="csrftoken=initial-csrf")
            if self.command != "GET":
                expected = "rotated-csrf" if "sessionid=verified" in self.headers.get("Cookie", "") else "initial-csrf"
                assert self.headers.get("X-CSRFToken") == expected
            if self.path == "/api/public/v1/facility/":
                return self.respond(state["facilities"])
            if self.path == native.KOLIBRI_QUEUE:
                return self.respond(state["jobs"])
            if self.path == "/api/tasks/tasks/":
                assert not state["facilities"] and not state["jobs"]
                assert payload["type"] == native.KOLIBRI_TASK
                assert payload["settings"] == {"learner_can_login_with_no_password": False,
                                               "learner_can_sign_up": False, "on_my_own_setup": False}
                assert payload["allow_guest_access"] is True and payload["is_soud"] is False
                state["username"] = payload["superuser"]["username"]
                state["password"] = payload["superuser"]["password"]
                state["facilities"] = [{"id": "facility-1", "learner_can_sign_up": state["signup"],
                                        "learner_can_login_with_no_password": state["blank"]}]
                state["jobs"] = [{"id": "task-1", "type": native.KOLIBRI_TASK,
                                  "status": state["task_status"], "kwargs": payload,
                                  "extra_metadata": {"username": state["username"], "facility_id": "facility-1"}}]
                return self.respond(state["jobs"][0])
            if self.path == "/api/tasks/tasks/task-1/":
                return self.respond(state["jobs"][0])
            if self.path == "/api/auth/session/":
                if payload != {"username": state.get("username"), "password": state["password"]}:
                    return self.respond({"secret": "native credential details"}, code=401)
                self.send_response(200)
                self.send_header("Set-Cookie", "csrftoken=rotated-csrf; Path=/")
                self.send_header("Set-Cookie", "sessionid=verified; Path=/")
                self.end_headers()
                self.wfile.write(json.dumps({"username": state["username"], "facility_id": "facility-1",
                                            "kind": ["superuser"] if state["admin"] else ["learner"]}).encode())
                return
            if self.path == "/api/tasks/tasks/clearall/":
                assert payload == {"queue": "device_provision"}
                assert "sessionid=verified" in self.headers.get("Cookie", "")
                if state["cleanup"]:
                    state["jobs"] = []
                return self.respond({})
            if self.path == "/api/device/devicesettings/":
                assert "sessionid=verified" in self.headers.get("Cookie", "")
                return self.respond({"allow_guest_access": state["guest"]})
            if self.path == "/api/auth/session/current/" and self.command == "DELETE":
                return self.respond([])
            return self.respond({}, code=404)

        do_GET = do_POST = do_PUT = do_DELETE = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setitem(native.BASE, "kolibri", "http://127.0.0.1:" + str(server.server_port))
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


def value(mode="create"):
    return {"mode": mode, "username": "operator", "password": "disposable-learning-password", "confirmed": True}


def provision(state):
    assert native.prepare("kolibri", value())["ok"]
    state["calls"].clear()


def test_create_uses_native_csrf_rotated_session_and_clears_only_provision_queue(kolibri):
    result = native.prepare("kolibri", value())
    assert result["ok"] and kolibri["jobs"] == []
    assert value()["password"] not in json.dumps(result)
    assert kolibri["calls"][-1] == ("DELETE", "/api/auth/session/current/")


def test_existing_account_verify_never_reprovisions(kolibri):
    provision(kolibri)
    assert native.prepare("kolibri", value("verify"))["ok"]
    assert ("POST", "/api/tasks/tasks/") not in kolibri["calls"]
    assert ("POST", "/api/tasks/tasks/clearall/") not in kolibri["calls"]
    with pytest.raises(native.SetupError, match="already has"):
        native.prepare("kolibri", value())


def test_unknown_account_is_not_reset_and_errors_are_redacted(kolibri):
    provision(kolibri)
    kolibri["password"] = "another existing password"
    with pytest.raises(native.NativeAuthError) as err:
        native.prepare("kolibri", value("verify"))
    assert "native credential details" not in str(err.value)
    assert ("POST", "/api/tasks/tasks/") not in kolibri["calls"]


@pytest.mark.parametrize("change", ["extra", "owner", "unfinished"])
def test_unknown_or_running_native_jobs_are_never_cleared(kolibri, change):
    provision(kolibri)
    job = {"id": "old-task", "type": native.KOLIBRI_TASK, "status": "COMPLETED",
           "extra_metadata": {"username": "operator", "facility_id": "facility-1"}}
    if change == "owner":
        job["extra_metadata"]["username"] = "someone else"
    if change == "unfinished":
        job["status"] = "RUNNING"
    kolibri["jobs"] = [job, dict(job)] if change == "extra" else [job]
    with pytest.raises(native.SetupError):
        native.prepare("kolibri", value("verify"))
    assert ("POST", "/api/tasks/tasks/clearall/") not in kolibri["calls"]


def test_interrupted_successful_setup_can_finish_cleanup_without_changing_account(kolibri):
    kolibri["cleanup"] = False
    with pytest.raises(native.SetupError, match="cleanup"):
        native.prepare("kolibri", value())
    assert kolibri["jobs"]
    kolibri["cleanup"] = True
    kolibri["calls"].clear()
    assert native.prepare("kolibri", value("verify"))["ok"]
    assert kolibri["jobs"] == []
    assert ("POST", "/api/tasks/tasks/") not in kolibri["calls"]


@pytest.mark.parametrize("setting", ["admin", "guest", "signup", "blank"])
def test_native_admin_and_learner_policy_fail_closed(kolibri, setting):
    kolibri[setting] = setting in {"signup", "blank"}
    with pytest.raises(native.SetupError):
        native.prepare("kolibri", value())
    assert kolibri["calls"][-1] == ("DELETE", "/api/auth/session/current/")


def test_failed_provision_does_not_claim_success_or_delete_unknown_state(kolibri):
    kolibri["task_status"] = "FAILED"
    with pytest.raises(native.SetupError, match="did not finish"):
        native.prepare("kolibri", value())
    assert ("POST", "/api/tasks/tasks/clearall/") not in kolibri["calls"]
