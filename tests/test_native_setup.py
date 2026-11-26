import json
from unittest.mock import Mock
import pytest
from worker import native_setup as native

PASSWORD="native-test-password-123!"
HOME={"username":"admin@aftergrid.home.arpa","password":PASSWORD,"current_password":""}
GROCY={"username":"admin","password":PASSWORD,"current_password":"admin"}

@pytest.mark.parametrize("ident,payload",[
 ("kiwix",HOME),("homebox",{**HOME,"password":"short"}),
 ("homebox",{**HOME,"username":"not-email"}),("homebox",{**HOME,"extra":"field"}),
 ("homebox",{**HOME,"current_password":"old"}),("grocy",{**GROCY,"username":"another"}),
 ("grocy",{**GROCY,"current_password":""}),("grocy",{**GROCY,"current_password":PASSWORD}),
 ("homebox",{**HOME,"password":True}),
])
def test_native_fields_fail_closed(ident,payload):
    with pytest.raises(ValueError):native.validate(ident,payload)

def test_homebox_new_account_and_idempotent_retry(monkeypatch):
    client=Mock()
    client.login.side_effect=[False,True]
    client.request.return_value=(204,b"","")
    monkeypatch.setattr(native,"NativeClient",lambda ident:client)
    native.configure("homebox",HOME)
    client.request.assert_called_once_with("POST","/api/v1/users/register",
        {"name":"AfterGrid household","email":HOME["username"],"password":PASSWORD})
    client.reset_mock(); client.login.side_effect=None; client.login.return_value=True
    native.configure("homebox",HOME)
    client.request.assert_not_called()

def test_homebox_failure_does_not_include_native_body_or_password(monkeypatch):
    client=Mock();client.login.return_value=False
    client.request.return_value=(500,PASSWORD.encode(),"")
    monkeypatch.setattr(native,"NativeClient",lambda ident:client)
    with pytest.raises(RuntimeError) as error:native.configure("homebox",HOME)
    assert PASSWORD not in str(error.value)

def test_grocy_changes_only_authenticated_admin_and_checks_new_and_old_password(monkeypatch):
    clients=[Mock() for _ in range(4)]
    clients[0].login.return_value=False
    clients[1].login.return_value=True
    clients[1].read_json.return_value=[{"id":1,"username":"admin","first_name":"Keep","last_name":"Name","picture_file_name":"portrait.png"}]
    clients[1].request.return_value=(204,b"","")
    clients[2].login.return_value=True
    clients[3].login.return_value=False
    factory=iter(clients);monkeypatch.setattr(native,"NativeClient",lambda ident:next(factory))
    native.configure("grocy",GROCY)
    clients[1].request.assert_called_once_with("PUT","/api/users/1",
        {"username":"admin","first_name":"Keep","last_name":"Name","picture_file_name":"portrait.png","password":PASSWORD})
    clients[2].login.assert_called_once_with("admin",PASSWORD)
    clients[3].login.assert_called_once_with("admin","admin")

def test_grocy_retry_does_not_reset_password(monkeypatch):
    clients=[Mock() for _ in range(3)]
    clients[0].login.return_value=True;clients[1].login.return_value=True;clients[2].login.return_value=False
    factory=iter(clients);monkeypatch.setattr(native,"NativeClient",lambda ident:next(factory))
    native.configure("grocy",GROCY)
    for client in clients:client.request.assert_not_called()

def test_grocy_refuses_another_native_identity(monkeypatch):
    clients=[Mock(),Mock()];clients[0].login.return_value=False;clients[1].login.return_value=True
    clients[1].read_json.return_value=[{"id":2,"username":"other"}]
    factory=iter(clients);monkeypatch.setattr(native,"NativeClient",lambda ident:next(factory))
    with pytest.raises(RuntimeError):native.configure("grocy",GROCY)
    clients[1].request.assert_not_called()

@pytest.mark.parametrize("location,works",[
 ("http://aftergrid-grocy/",True),("http://aftergrid-grocy:80/",True),
 ("/login?invalid=true",False),
])
def test_grocy_login_recognizes_native_destinations(location,works,monkeypatch):
    client=native.NativeClient("grocy")
    monkeypatch.setattr(client,"request",lambda *a,**kw:(302,b"",location))
    assert client.login("admin",PASSWORD) is works

def test_native_login_never_follows_external_redirect(monkeypatch):
    client=native.NativeClient("grocy")
    request=Mock(return_value=(302,b"", "https://external.example/"))
    monkeypatch.setattr(client,"request",request)
    with pytest.raises(RuntimeError):client.login("admin",PASSWORD)
    assert request.call_count==1
    assert native.NoRedirect().redirect_request(None,None,None,None,None,None) is None

def test_registration_closure_is_verified_without_creating_account(monkeypatch):
    client=Mock();client.login.return_value=True;client.request.return_value=(403,b"","")
    monkeypatch.setattr(native,"NativeClient",lambda ident:client)
    native.verify_closed_homebox(HOME)
    client.request.assert_called_once_with("POST","/api/v1/users/register",{})
    client.request.return_value=(400,b"","")
    with pytest.raises(RuntimeError):native.verify_closed_homebox(HOME)

def test_homebox_uses_native_bearer_token_for_authenticated_request(monkeypatch):
    # Real urllib transport: simulate the upstream single-label Domain cookie.
    # The authenticated endpoint requires the documented native bearer token.
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Set-Cookie","hb.auth.token=fixture-token; Domain=aftergrid-homebox; Path=/")
            self.end_headers()
            self.wfile.write(b'{"token":"Bearer fixture-token"}')
        def do_GET(self):
            accepted=self.headers.get("Authorization")=="Bearer fixture-token"
            self.send_response(200 if accepted else 401);self.end_headers()
            self.wfile.write(json.dumps({"item":{"email":HOME["username"]}}).encode())
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setitem(native.NativeClient.BASES,"homebox","http://127.0.0.1:"+str(server.server_port))
    try:assert native.NativeClient("homebox").login(HOME["username"],PASSWORD)
    finally:server.shutdown();server.server_close();thread.join(timeout=2)

@pytest.mark.parametrize("raw",[b"{}",b'{"token":"Bearer x\\r\\nInjected: yes"}',b'{"token":123}',b"not-json"])
def test_homebox_invalid_native_token_never_reaches_account_endpoint(raw,monkeypatch):
    client=native.NativeClient("homebox")
    request=Mock(return_value=(200,raw,""))
    monkeypatch.setattr(client,"request",request)
    with pytest.raises(RuntimeError):client.login(HOME["username"],PASSWORD)
    assert request.call_count==1 and client.authorization is None
