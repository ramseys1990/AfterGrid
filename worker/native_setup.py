"""Native first-run account setup over fixed, private application endpoints.

Passwords are request data only. Never include native response bodies in errors.
"""
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request


def validate(ident, payload):
    if ident not in {"homebox", "grocy"} or not isinstance(payload, dict) or set(payload) != {"username", "password", "current_password"}:
        raise ValueError("Unsupported native account setup")
    if any(not isinstance(value, str) for value in payload.values()):
        raise ValueError("Invalid native account fields")
    username, password, current = (payload[k] for k in ("username", "password", "current_password"))
    if not 12 <= len(password) <= 128 or len(current) > 128:
        raise ValueError("Use a native password of 12 to 128 characters")
    if ident == "homebox":
        if current or len(username) > 254 or not re.fullmatch(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", username):
            raise ValueError("Use a local Homebox sign-in email")
    elif username != "admin" or not current or password == current:
        raise ValueError("Provide the current Grocy administrator password and a different new password")
    return payload


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class NativeClient:
    BASES = {"homebox": "http://aftergrid-homebox:7745", "grocy": "http://aftergrid-grocy:80"}

    def __init__(self, ident):
        self.ident = ident
        self.base = self.BASES[ident]
        self.client = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(self, method, path, payload=None, form=False):
        if not path.startswith("/") or path.startswith("//") or "?" in path:
            raise ValueError("Unsupported native endpoint")
        body = None if payload is None else (
            urllib.parse.urlencode(payload).encode() if form else json.dumps(payload).encode())
        request = urllib.request.Request(self.base + path, data=body, method=method,
            headers={"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"})
        try:
            try:
                response = self.client.open(request, timeout=12)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise RuntimeError("Native setup response exceeded its limit")
                return response.status, raw, response.headers.get("Location", "")
        except (OSError, urllib.error.URLError):
            raise RuntimeError("Native application unavailable; inspect its readiness before retrying") from None

    def read_json(self, method, path, payload=None):
        code, raw, _ = self.request(method, path, payload)
        if code != 200:
            raise RuntimeError("Native authenticated account check failed")
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise RuntimeError("Native account response was invalid") from None

    def login(self, username, password):
        if self.ident == "homebox":
            code, _, _ = self.request("POST", "/api/v1/users/login",
                                      {"username": username, "password": password, "stayLoggedIn": False})
            if code == 401:
                return False
            if code != 200:
                raise RuntimeError("Native Homebox sign-in unavailable")
            account = self.read_json("GET", "/api/v1/users/self")
            return isinstance(account, dict) and isinstance(account.get("item"), dict) and account["item"].get("email", "").lower() == username.lower()
        code, _, location = self.request("POST", "/login",
                                         {"username": username, "password": password}, form=True)
        if code != 302:
            raise RuntimeError("Native Grocy sign-in unavailable")
        target = urllib.parse.urlsplit(urllib.parse.urljoin(self.base, location))
        base = urllib.parse.urlsplit(self.base)
        if (target.scheme, target.hostname, target.port) != (base.scheme, base.hostname, base.port):
            raise RuntimeError("Native Grocy sign-in returned an unexpected destination")
        if target.path == "/login":
            return False
        if target.path != "/" or target.query or target.fragment:
            raise RuntimeError("Native Grocy sign-in returned an unexpected destination")
        return True


def configure(ident, payload):
    validate(ident, payload)
    username, password = payload["username"], payload["password"]
    client = NativeClient(ident)
    if ident == "homebox":
        if not client.login(username, password):
            code, _, _ = client.request("POST", "/api/v1/users/register",
                {"name": "AfterGrid household", "email": username, "password": password})
            if code != 204 or not client.login(username, password):
                raise RuntimeError("Homebox account setup was not confirmed. If the account exists, use its native password.")
        return
    # A retry after an ambiguous password-change response must verify the new
    # password first, rather than resetting any other native account.
    if not client.login(username, password):
        client = NativeClient(ident)
        if not client.login(username, payload["current_password"]):
            raise RuntimeError("Grocy current administrator password was not accepted")
        users = client.read_json("GET", "/api/user")
        if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
            raise RuntimeError("Native Grocy administrator identity was not confirmed")
        account = users[0]
        if type(account.get("id")) is not int or account["id"] <= 0 or account.get("username") != "admin":
            raise RuntimeError("Native Grocy administrator identity was not confirmed")
        update = {key: account.get(key) for key in ("username", "first_name", "last_name", "picture_file_name")}
        update["password"] = password
        code, _, _ = client.request("PUT", "/api/users/" + str(account["id"]), update)
        if code not in {200, 204}:
            raise RuntimeError("Grocy password change was not confirmed; inspect native sign-in before retrying")
    fresh = NativeClient(ident)
    if not fresh.login(username, password):
        raise RuntimeError("Grocy new password sign-in was not confirmed; inspect before retrying")
    if NativeClient(ident).login(username, payload["current_password"]):
        raise RuntimeError("Grocy old password still works; keep the application local-only")


def verify_closed_homebox(payload):
    client = NativeClient("homebox")
    if not client.login(payload["username"], payload["password"]):
        raise RuntimeError("Homebox sign-in after closing registration was not confirmed")
    # An empty registration cannot create an account. The pinned native API
    # decodes it before checking its disabled-registration setting.
    code, _, _ = client.request("POST", "/api/v1/users/register", {})
    if code != 403:
        raise RuntimeError("Homebox registration closure was not confirmed; keep it local-only")
