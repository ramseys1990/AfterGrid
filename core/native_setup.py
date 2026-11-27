"""Bounded native account setup; credentials never enter worker jobs or storage."""
import base64
import http.cookiejar
from html.parser import HTMLParser
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = {"homebox": "http://aftergrid-homebox:7745", "grocy": "http://aftergrid-grocy",
        "media": "http://aftergrid-media:8096", "kolibri": "http://aftergrid-kolibri:8086",
        "notes": "http://aftergrid-notes:8080"}
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
        self.notes_logout_token = None

    def request(self, path, payload=None, method=None, form=False, redirect=False, text=False):
        headers = {"Accept": "text/html" if self.module == "notes" and text else "application/json",
                   "User-Agent": "AfterGrid-native-setup"}
        body = None
        if payload is not None:
            body = (urllib.parse.urlencode(payload) if form else json.dumps(payload)).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        if self.authorization:
            headers["Authorization"] = self.authorization
        if self.module == "kolibri":
            for cookie in self.cookies:
                if cookie.name == "kolibri_csrftoken":
                    headers["X-CSRFToken"] = cookie.value
        req = urllib.request.Request(BASE[self.module] + path, data=body,
                                     headers=headers, method=method or ("POST" if body else "GET"))
        try:
            response = self.opener.open(req, timeout=8)
        except urllib.error.HTTPError as exc:
            location = urllib.parse.urljoin(BASE[self.module] + path, exc.headers.get("Location", ""))
            if self.module == "grocy" and path == "/login" and exc.code in (302, 303) and location == BASE[self.module] + "/login?invalid=true":
                exc.close()
                raise NativeAuthError("Native login refused. Check your account details.") from None
            if self.module == "media" and path == "/Users/AuthenticateByName" and exc.code in (401, 403):
                exc.close()
                raise NativeAuthError("Native login refused. Check your account details.") from None
            if self.module == "kolibri" and path == "/api/auth/session/" and exc.code in (400, 401):
                exc.close()
                raise NativeAuthError("Native login refused. Check your account details.") from None
            if redirect and exc.code in (302, 303) and location == BASE[self.module] + "/":
                exc.close()
                return None
            if (redirect and self.module == "notes" and exc.code in (302, 303)
                and urllib.parse.urlsplit(location).netloc == urllib.parse.urlsplit(BASE[self.module]).netloc
                and urllib.parse.urlsplit(location).path == "/doku.php"):
                exc.close()
                return None
            code = exc.code
            exc.close()
            raise SetupError("Native request refused (HTTP " + str(code) + "). Check the account details and application status.") from None
        except (OSError, ValueError):
            raise SetupError("Native application unavailable. Check its status and try again.") from None
        with response:
            limit = 1024 * 1024 if self.module == "notes" and text else MAX_BYTES
            raw = response.read(limit + 1)
            if len(raw) > limit:
                raise SetupError("Unexpected native response size")
            if not raw:
                return None
            try:
                if self.module == "notes" and text:
                    return raw.decode("utf-8")
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
            elif self.module == "kolibri" and list(self.cookies):
                self.request("/api/auth/session/current/", {}, method="DELETE")
            elif self.module == "notes" and self.notes_logout_token:
                self.request("/doku.php", {"do": "logout", "sectok": self.notes_logout_token},
                             form=True, redirect=True, text=True)
        except SetupError:
            pass
        self.cookies.clear()
        self.authorization = None
        self.media_authenticated = False
        self.notes_logout_token = None


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
             "media": {"create", "finish-setup", "verify"}, "kolibri": {"create", "verify"},
             "notes": {"create", "verify"}}
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
    if module == "notes" and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", username):
        raise ValueError("Use a lowercase native username with letters, numbers, dots, hyphens or underscores")
    return value


class NotesPage(HTMLParser):
    """Only native form controls; no script execution, assets or forwarded pages."""
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.ids, self.inputs, self.forms, self.links = set(), [], {}, []
        self.form = self.select = self.textarea = None
        self.feed(source or "")

    def add(self, name, value, form=None):
        target = self.form if form is None else form
        if target is not None and name:
            self.forms[target].append((name, value))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "form":
            self.form = a.get("id") or "form-" + str(len(self.forms))
            self.forms[self.form] = []
        elif tag == "input":
            self.inputs.append(a)
            if "disabled" not in a and (a.get("type") not in {"checkbox", "radio"} or "checked" in a):
                self.add(a.get("name"), a.get("value", ""))
        elif tag == "select":
            self.select = {"attrs": a, "values": [], "first": None, "form": self.form}
        elif tag == "option" and self.select is not None:
            value = a.get("value", "")
            if self.select["first"] is None:
                self.select["first"] = value
            if "selected" in a:
                self.select["values"].append(value)
        elif tag == "textarea":
            self.textarea = (a, [], self.form)

    def handle_data(self, data):
        if self.textarea is not None:
            self.textarea[1].append(data)

    def handle_endtag(self, tag):
        if tag == "select" and self.select is not None:
            s = self.select
            values = s["values"] or ([] if "multiple" in s["attrs"] else [s["first"] or ""])
            if "disabled" not in s["attrs"]:
                for value in values:
                    self.add(s["attrs"].get("name"), value, s["form"])
            self.select = None
        elif tag == "textarea" and self.textarea is not None:
            a, parts, form = self.textarea
            if "disabled" not in a:
                self.add(a.get("name"), "".join(parts), form)
            self.textarea = None
        elif tag == "form":
            self.form = None

    def checked(self, name, value):
        return any(a.get("name") == name and a.get("value", "") == value and "checked" in a for a in self.inputs)


def notes_page(client, path):
    page = NotesPage(client.request(path, text=True))
    for link in page.links:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)
        token = query.get("sectok", [""])[0]
        if query.get("do") == ["logout"] and re.fullmatch(r"[a-f0-9]{32}", token):
            client.notes_logout_token = token
    return page


def notes_setup(client, value):
    if value["mode"] == "create":
        page = notes_page(client, "/install.php")
        names = {a.get("name") for a in page.inputs}
        if not {"d[title]", "d[superuser]", "d[password]", "d[acl]"} <= names:
            raise SetupError("DokuWiki is already configured or setup is unavailable; use Verify existing account")
        if not any(a.get("name") == "d[license]" and a.get("value") == "0" for a in page.inputs):
            raise SetupError("DokuWiki installer options changed; keep the application local-only")
        client.request("/install.php", {"l": "en", "submit": "Save", "d[title]": "AfterGrid notes",
            "d[acl]": "1", "d[superuser]": value["username"], "d[fullname]": value["username"],
            "d[email]": value["username"] + "@aftergrid.home.arpa", "d[password]": value["password"],
            "d[confirm]": value["password"], "d[policy]": "2", "d[license]": "0"}, form=True, text=True)
    login = notes_page(client, "/doku.php?do=login")
    controls = login.forms.get("dw__login")
    token = next((v for k, v in controls or [] if k == "sectok"), "")
    if not controls or not re.fullmatch(r"[a-f0-9]{32}", token):
        raise SetupError("DokuWiki native login form could not be verified")
    client.request("/doku.php", {"id": "start", "do": "login", "sectok": token,
        "u": value["username"], "p": value["password"]}, form=True, redirect=True, text=True)
    acl = notes_page(client, "/doku.php?do=admin&page=acl")
    if not {"acl__tree", "acl__detail"} <= acl.ids:
        raise NativeAuthError("DokuWiki administrator login refused. Check your account details.")
    config_path = "/doku.php?do=admin&page=config"
    config = notes_page(client, config_path)
    controls = config.forms.get("dw__configform")
    if not controls:
        raise SetupError("DokuWiki administrator configuration access could not be verified")
    if value["mode"] == "create":
        # Submit the native form's current controls; change only its update check.
        # The installer already set ACLs/closed policy and disabled registration.
        fields = [(k, v) for k, v in controls if k != "config[updatecheck]"]
        fields.append(("config[updatecheck]", "0"))
        fields.append(("submit", "Save"))
        client.request("/doku.php", fields, form=True, redirect=True, text=True)
        config = notes_page(client, config_path)
        acl = notes_page(client, "/doku.php?do=admin&page=acl")
    if (not config.checked("config[useacl]", "1")
        or not config.checked("config[disableactions][]", "register")
        or not any(a.get("name") == "config[updatecheck]" for a in config.inputs)
        or config.checked("config[updatecheck]", "1")
        or not acl.checked("acl[*][@ALL]", "0")
        or any(a.get("name", "").startswith("acl[") and a.get("name", "").endswith("[@ALL]")
               and "checked" in a and a.get("value") != "0" for a in acl.inputs)):
        raise SetupError("DokuWiki must use closed ACLs, disabled registration and disabled online update checks before sharing")
    guest = NativeClient("notes")
    try:
        anonymous = notes_page(guest, "/doku.php?id=aftergrid:access-check")
        if "dw__login" not in anonymous.forms:
            raise SetupError("Anonymous DokuWiki access was not refused; keep it local-only")
    finally:
        guest.close()
    return {"ok": True, "message": "DokuWiki administrator login, closed access controls and anonymous-access refusal verified. Registration and online update checks are disabled. Save your native credentials, then use Share on LAN. No publishing license was assigned; create household users and review permissions inside DokuWiki."}


KOLIBRI_TASK = "kolibri.core.device.tasks.provisiondevice"
KOLIBRI_QUEUE = "/api/tasks/tasks/?queue=device_provision"


def kolibri_login(client, username, password):
    user = client.request("/api/auth/session/", {"username": username, "password": password})
    if (not isinstance(user, dict) or user.get("username") != username
        or not isinstance(user.get("kind"), list) or "superuser" not in user["kind"]
        or not isinstance(user.get("facility_id"), str) or not user["facility_id"]):
        raise SetupError("A Kolibri device administrator is required")
    return user


def kolibri_clear_setup(client, user, task_id=None):
    # Match the native wizard's fixed provisioning-queue cleanup. Its completed
    # task can contain the submitted credential; never return task details.
    jobs = client.request(KOLIBRI_QUEUE)
    if jobs == []:
        return
    if not isinstance(jobs, list) or len(jobs) != 1 or not isinstance(jobs[0], dict):
        raise SetupError("Kolibri setup tasks need review; keep the application local-only")
    job = jobs[0]
    metadata = job.get("extra_metadata")
    if (job.get("type") != KOLIBRI_TASK or job.get("status") != "COMPLETED"
        or (task_id is not None and job.get("id") != task_id)
        or not isinstance(metadata, dict) or metadata.get("username") != user["username"]
        or metadata.get("facility_id") != user["facility_id"]):
        raise SetupError("Kolibri setup is incomplete or belongs to another account; keep it local-only")
    client.request("/api/tasks/tasks/clearall/", {"queue": "device_provision"})
    if client.request(KOLIBRI_QUEUE) != []:
        raise SetupError("Kolibri setup cleanup could not be verified; keep it local-only")


def kolibri_setup(client, value):
    username, password = value["username"], value["password"]
    # Native session update issues the CSRF cookie, including before provisioning.
    client.request("/api/auth/session/current/", {}, method="PUT")
    task_id = None
    if value["mode"] == "create":
        if client.request("/api/public/v1/facility/") != [] or client.request(KOLIBRI_QUEUE) != []:
            raise SetupError("Kolibri already has facility or setup state; use Verify existing account")
        job = client.request("/api/tasks/tasks/", {
            "type": KOLIBRI_TASK, "facility": {"name": "AfterGrid learning"},
            "preset": "nonformal", "superuser": {"username": username, "password": password,
                                                       "full_name": "AfterGrid administrator"},
            "language_id": "en", "device_name": "AfterGrid learning",
            "settings": {"learner_can_login_with_no_password": False,
                         "learner_can_sign_up": False, "on_my_own_setup": False},
            "allow_guest_access": True, "is_provisioned": True, "is_soud": False})
        task_id = job.get("id") if isinstance(job, dict) else None
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", task_id):
            raise SetupError("Kolibri setup was submitted; verify the existing account before retrying")
        deadline = time.monotonic() + 40
        while True:
            job = client.request("/api/tasks/tasks/" + task_id + "/")
            if not isinstance(job, dict) or job.get("id") != task_id or job.get("type") != KOLIBRI_TASK:
                raise SetupError("Kolibri setup status could not be verified; keep it local-only")
            if job.get("status") == "COMPLETED":
                break
            if job.get("status") in {"FAILED", "CANCELED"} or time.monotonic() >= deadline:
                raise SetupError("Kolibri setup did not finish; keep it local-only and verify existing credentials before retrying")
            time.sleep(0.5)
    user = kolibri_login(client, username, password)
    settings = client.request("/api/device/devicesettings/")
    if value["mode"] == "create":
        extra = settings.get("extra_settings") if isinstance(settings, dict) else None
        if not isinstance(extra, dict):
            raise SetupError("Kolibri download settings could not be read; keep it local-only")
        client.request("/api/device/devicesettings/", {"extra_settings": {
            **extra, "enable_automatic_download": False, "allow_learner_download_resources": False,
            "allow_download_on_metered_connection": False}}, method="PATCH")
        settings = client.request("/api/device/devicesettings/")
    kolibri_clear_setup(client, user, task_id)
    if not isinstance(settings, dict) or settings.get("allow_guest_access") is not True:
        raise SetupError("Enable native guest reading in Kolibri before sharing")
    extra = settings.get("extra_settings")
    if (not isinstance(extra, dict) or any(extra.get(key) is not False for key in
        ("enable_automatic_download", "allow_learner_download_resources", "allow_download_on_metered_connection"))):
        raise SetupError("Disable native automatic, learner-requested and metered-connection downloads in Kolibri before sharing")
    facilities = client.request("/api/public/v1/facility/")
    facility = next((f for f in facilities if isinstance(f, dict) and f.get("id") == user["facility_id"]), None) if isinstance(facilities, list) else None
    if (not facility or facility.get("learner_can_sign_up") is not False
        or facility.get("learner_can_login_with_no_password") is not False):
        raise SetupError("Disable native learner self-registration and passwordless learner login before sharing")
    return {"ok": True, "message": "Kolibri device administrator login and setup cleanup verified. Guest reading is enabled; learner accounts require passwords and self-registration is disabled. Automatic and learner-requested downloads are disabled. Save your credentials, then use Share on LAN. Import educational channels in Kolibri; no content is installed yet."}


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


def media_login(client, username, password, require_password=True):
    if client.media_authenticated:
        client.request("/Sessions/Logout", {})
        client.media_authenticated = False
        client.authorization = MEDIA_AUTH
    result = client.request("/Users/AuthenticateByName", {"Username": username, "Pw": password})
    token = result.get("AccessToken") if isinstance(result, dict) else None
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", token):
        raise SetupError("Jellyfin login could not be verified")
    client.authorization = MEDIA_AUTH + ', Token="' + token + '"'
    client.media_authenticated = True
    user = client.request("/Users/Me")
    if (not isinstance(user, dict) or user.get("Name") != username
        or (require_password and user.get("HasPassword") is not True) or not isinstance(user.get("Policy"), dict)
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
            if not isinstance(initial, dict) or not isinstance(initial.get("Name"), str) or not initial["Name"]:
                raise SetupError("Jellyfin initial account could not be identified")
            # The initial administrator is hidden from /Users/Public. Verify its
            # native empty first-run credential instead; never reset an unknown
            # password after a partial setup attempt.
            check = NativeClient("media")
            try:
                try:
                    media_login(check, initial["Name"], "", require_password=False)
                except NativeAuthError:
                    raise SetupError("Jellyfin already has an account; use Finish interrupted setup with its existing credentials") from None
            finally:
                check.close()
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
        media_login(client, username, password)
    network = client.request("/System/Configuration/network")
    if not isinstance(network, dict) or network.get("EnableRemoteAccess") is not False:
        raise SetupError("Disable Jellyfin remote access in its native settings before sharing")
    check = NativeClient("media")
    try:
        try:
            media_login(check, username, "", require_password=False)
        except NativeAuthError:
            pass
        else:
            raise SetupError("Jellyfin still accepts an empty password; keep it local-only")
    finally:
        check.close()
    return {"ok": True, "message": "Jellyfin administrator login and completed setup verified; remote access is disabled. Save your native credentials, then use Share on LAN. In Jellyfin, add /media and disable internet providers for offline libraries. Native login remains required."}


def prepare(module, value):
    value = validate(module, value)
    mode, username, password = value["mode"], value["username"], value["password"]
    client = NativeClient(module)
    created = False
    try:
        if module == "notes":
            return notes_setup(client, value)
        if module == "kolibri":
            return kolibri_setup(client, value)
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
