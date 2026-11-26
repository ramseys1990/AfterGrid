"""Bounded native account setup; credentials never enter worker jobs or storage."""
import base64
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = {"homebox": "http://aftergrid-homebox:7745", "grocy": "http://aftergrid-grocy",
        "media": "http://aftergrid-media:8096"}
MEDIA_AUTH = 'MediaBrowser Client="AfterGrid", Device="Native setup", DeviceId="aftergrid-native-setup", Version="1.0"'
MAX_BYTES = 256 * 1024


class SetupError(Exception):
    pass


class NativeAuthError(SetupError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class NativeClient:
    def __init__(self, module):
        self.module = module
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPCookieProcessor(self.cookies))
        self.authorization = MEDIA_AUTH if module == "media" else None
        self.media_authenticated = False

    def request(self, path, payload=None, method=None, form=False, redirect=False):
        headers = {"Accept": "application/json", "User-Agent": "AfterGrid-native-setup"}
        body = None
        if payload is not None:
            body = (urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        if self.authorization:
            headers["Authorization"] = self.authorization
        req = urllib.request.Request(BASE[self.module] + path, data=body,
                                     headers=headers, method=method or ("POST" if body else "GET"))
        try:
            response = self.opener.open(req, timeout=8)
        except urllib.error.HTTPError as exc:
            location = urllib.parse.urljoin(BASE[self.module] + path, exc.headers.get("Location", ""))
            if self.module == "grocy" and path == "/login" and exc.code in (302, 303) and location == BASE[self.module] + "/login?invalid=true":
                exc.close()
                raise NativeAuthError("Native login refused. Check your account details.") from None
            if redirect and exc.code in (302, 303) and location == BASE[self.module] + "/":
                exc.close()
                return None
            code = exc.code
            exc.close()
            raise SetupError("Native request refused (HTTP " + str(code) + "). Check the account details and application status.") from None
        except (OSError, ValueError):
            raise SetupError("Native application unavailable. Check its status and try again.") from None
        with response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise SetupError("Unexpected native response size")
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (ValueError, UnicodeError):
                raise SetupError("Unexpected native response. Check the application before retrying.") from None

    def close(self):
        try:
            if self.module == "homebox" and self.authorization:
                self.request("/api/v1/users/logout", {}, method="POST")
            elif self.module == "grocy" and list(self.cookies):
                self.request("/logout", redirect=True)
            elif self.module == "media" and self.media_authenticated:
                self.request("/Sessions/Logout", {})
        except SetupError:
            pass
        self.cookies.clear()
        self.authorization = None
        self.media_authenticated = False


def validate(module, value):
    # Do not use request-model errors that echo a submitted credential.
    if module not in BASE or not isinstance(value, dict):
        raise ValueError("Unsupported native setup")
    mode = value.get("mode")
    allowed = {"mode", "username", "password", "confirmed"}
    if module == "homebox" and mode == "create":
        allowed.add("name")
    if set(value) != allowed or value.get("confirmed") is not True:
        raise ValueError("Confirm native account setup on this trusted LAN")
    modes = {"homebox": {"create", "verify"}, "grocy": {"secure-default", "verify"},
             "media": {"create", "finish-setup", "verify"}}
    if mode not in modes[module]:
        raise ValueError("Unsupported native setup action")
    username, password = value.get("username"), value.get("password")
    if not isinstance(username, str) or not 1 <= len(username) <= 254 or username != username.strip():
        raise ValueError("Enter a valid native account name")
    if not isinstance(password, str) or not 1 <= len(password) <= 256 or any(ord(c) < 32 for c in password):
        raise ValueError("Enter a native password without control characters")
    if mode in {"create", "secure-default"} and len(password) < 12:
        raise ValueError("Choose a password of at least 12 characters")
    if module == "homebox" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", username):
        raise ValueError("Homebox uses an email address for its local account")
    if module == "homebox" and mode == "create":
        if not isinstance(value["name"], str) or not 1 <= len(value["name"].strip()) <= 80:
            raise ValueError("Enter a Homebox display name")
    if module == "grocy" and (username != "admin" or password == "admin"):
        raise ValueError("Use the native admin account with a non-default password")
    return value


def homebox_login(client, username, password):
    result = client.request("/api/v1/users/login", {"username": username, "password": password, "stayLoggedIn": False})
    token = result.get("token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token.startswith("Bearer ") or not 8 < len(token) <= 2048 or "\n" in token or "\r" in token:
        raise SetupError("Native login could not be verified")
    client.authorization = token
    result = client.request("/api/v1/users/self")
    if not isinstance(result, dict) or not isinstance(result.get("item"), dict) or result["item"].get("email", "").casefold() != username.casefold():
        raise SetupError("Native account identity could not be verified")


def grocy_login(client, password):
    encoded = base64.b64encode(password.encode()).decode()
    client.request("/login", {"username": "admin", "password_base64": encoded}, form=True, redirect=True)
    result = client.request("/api/user")
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict) or result[0].get("username") != "admin":
        raise SetupError("Native administrator login could not be verified")
    user = result[0]
    if not str(user.get("id", "")).isdigit():
        raise SetupError("Native administrator identity could not be verified")
    return user


def media_login(client, username, password):
    result = client.request("/Users/AuthenticateByName", {"Username": username, "Pw": password})
    token = result.get("AccessToken") if isinstance(result, dict) else None
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", token):
        raise SetupError("Jellyfin login could not be verified")
    client.authorization = MEDIA_AUTH + ', Token="' + token + '"'
    client.media_authenticated = True
    user = client.request("/Users/Me")
    if (not isinstance(user, dict) or user.get("Name") != username
        or user.get("HasPassword") is not True or not isinstance(user.get("Policy"), dict)
        or user["Policy"].get("IsAdministrator") is not True):
        raise SetupError("A password-protected Jellyfin administrator is required")


def media_setup(client, value):
    mode, username, password = value["mode"], value["username"], value["password"]
    public = client.request("/System/Info/Public")
    complete = public.get("StartupWizardCompleted") if isinstance(public, dict) else None
    if type(complete) is not bool:
        raise SetupError("Jellyfin startup status could not be verified")
    if mode == "verify":
        media_login(client, username, password)
        if not complete:
            raise SetupError("Account login verified; choose Finish interrupted setup before sharing")
    else:
        if complete:
            raise SetupError("Jellyfin is already configured; use Verify existing account")
        if mode == "create":
            initial = client.request("/Startup/User")
            users = client.request("/Users/Public")
            # Refuse an unknown or already password-protected first account.
            # Never reset credentials after partial setup or on an existing server.
            if (not isinstance(initial, dict) or not isinstance(initial.get("Name"), str)
                or not initial["Name"] or not isinstance(users, list) or len(users) != 1
                or not isinstance(users[0], dict) or users[0].get("Name") != initial.get("Name")
                or users[0].get("HasPassword") is not False
                or users[0].get("HasConfiguredPassword") is not False):
                raise SetupError("Jellyfin already has an account or unknown setup state; use Finish interrupted setup with its existing credentials")
            client.request("/Startup/User", {"Name": username, "Password": password})
        media_login(client, username, password)
        client.request("/Startup/RemoteAccess", {"EnableRemoteAccess": False})
        network = client.request("/System/Configuration/network")
        if not isinstance(network, dict) or network.get("EnableRemoteAccess") is not False:
            raise SetupError("Jellyfin remote access could not be confirmed disabled")
        client.request("/Startup/Complete", {})
        public = client.request("/System/Info/Public")
        if not isinstance(public, dict) or public.get("StartupWizardCompleted") is not True:
            raise SetupError("Jellyfin startup completion could not be verified")
    network = client.request("/System/Configuration/network")
    if not isinstance(network, dict) or network.get("EnableRemoteAccess") is not False:
        raise SetupError("Disable Jellyfin remote access in its native settings before sharing")
    return {"ok": True, "message": "Jellyfin administrator login and completed setup verified; remote access is disabled. Save your native credentials, then use Share on LAN. In Jellyfin, add /media and disable internet providers for offline libraries. Native login remains required."}


def prepare(module, value):
    value = validate(module, value)
    mode, username, password = value["mode"], value["username"], value["password"]
    client = NativeClient(module)
    created = False
    try:
        if module == "media":
            return media_setup(client, value)
        if module == "homebox":
            if mode == "create":
                client.request("/api/v1/users/register", {"name": value["name"].strip(), "email": username, "password": password})
                created = True
            homebox_login(client, username, password)
        else:
            if mode == "secure-default":
                user = grocy_login(client, "admin")
                client.request("/api/users/" + str(user["id"]), {
                    "username": "admin", "first_name": user.get("first_name") or "",
                    "last_name": user.get("last_name") or "", "picture_file_name": user.get("picture_file_name"),
                    "password_base64": base64.b64encode(password.encode()).decode()}, method="PUT")
                created = True
                client.close()
                client = NativeClient(module)
            grocy_login(client, password)
            # A verified new credential alone is not proof the default is gone.
            check = NativeClient(module)
            try:
                try:
                    grocy_login(check, "admin")
                except NativeAuthError:
                    pass
                else:
                    raise SetupError("Grocy still accepts its default password; keep it local-only")
            finally:
                check.close()
        return {"ok": True, "message": "Native account login verified. Save your native credentials, then use Share on LAN in the application card. Native login remains required."}
    except SetupError:
        if created:
            raise SetupError("The native account change was submitted, but verification did not finish. Use Verify existing account with the same credentials; do not create or reset it again.") from None
        raise
    finally:
        client.close()

