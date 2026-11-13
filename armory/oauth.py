"""Signing in to Nexus Mods with OAuth 2.0 + PKCE (RFC 6749 / 7636 / 8252), the way registered apps do.

Nexus gives each registered app a client id and the redirect address it may use. Until Armory is
registered, CLIENT_ID is empty and Settings offers the personal API key instead. A developer build
can set "nexus_client_id" (and "nexus_redirect") in config.json.

The flow: open the Nexus sign-in page in the browser with a one-time code challenge and a random
state; Nexus sends the browser back to a small server on 127.0.0.1 with a code; the code and the
secret verifier are exchanged for an access token (about 6 hours) and a refresh token.
"""
import base64
import hashlib
import http.server
import secrets as rnd
import threading
import time
import urllib.parse

from . import config, vault
from .net import NetError, get_json

AUTHORIZE = "https://users.nexusmods.com/oauth/authorize"
TOKEN = "https://users.nexusmods.com/oauth/token"
REVOKE = "https://users.nexusmods.com/oauth/revoke"
USERINFO = "https://users.nexusmods.com/oauth/userinfo"
SCOPES = "openid profile public"

# filled in once Nexus Mods registers Armory
CLIENT_ID = ""
REDIRECT = "http://127.0.0.1:7901/callback"


def client_id():
    return config.get("nexus_client_id") or CLIENT_ID


def redirect_uri():
    return config.get("nexus_redirect") or REDIRECT


def available():
    return bool(client_id())


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


PAGE = """<!doctype html><meta charset="utf-8"><title>Armory</title>
<body style="background:#111115;color:#e8e8ef;font:16px sans-serif;display:grid;place-items:center;height:90vh">
<div style="text-align:center"><h2>{title}</h2><p style="color:#8a8a99">{text}</p></div>"""


class _Catch(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server's name
        u = urllib.parse.urlparse(self.path)
        if u.path != self.server.path:
            self.send_error(404)
            return
        q = urllib.parse.parse_qs(u.query)
        ok = q.get("state", [""])[0] == self.server.state
        if ok:
            # a request without our state (another page poking the port) is ignored
            self.server.result = {k: v[0] for k, v in q.items()}
        ok = ok and "code" in q
        body = PAGE.format(title="Signed in" if ok else "Sign-in didn't work",
                           text="You can close this tab and go back to Armory." if ok else
                           "Go back to Armory and try again.").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def login(open_url, cancelled=lambda: False, timeout=300):
    """the whole browser sign-in; returns the tokens (also stored). Runs in a worker thread."""
    cid = client_id()
    if not cid:
        raise NetError("Armory isn't registered with Nexus Mods yet: use an API key")
    red = urllib.parse.urlparse(redirect_uri())
    verifier = _b64(rnd.token_bytes(48))
    state = _b64(rnd.token_bytes(24))
    try:
        srv = http.server.HTTPServer((red.hostname, red.port or 80), _Catch)
    except OSError as e:
        raise NetError(f"Couldn't listen on {red.hostname}:{red.port} for the sign-in ({e})") from None
    srv.state, srv.path, srv.result = state, red.path or "/", None
    srv.timeout = 0.5
    url = AUTHORIZE + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect_uri(), "scope": SCOPES,
        "state": state, "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256"})
    open_url(url)
    end = time.time() + timeout
    try:
        while srv.result is None:
            if cancelled() or time.time() > end:
                raise NetError("Sign-in cancelled" if cancelled() else "Sign-in timed out")
            srv.handle_request()
    finally:
        srv.server_close()
    res = srv.result
    if res.get("state") != state:
        raise NetError("The sign-in answer didn't match (state). Try again.")
    if "code" not in res:
        raise NetError(f"Nexus said no: {res.get('error_description') or res.get('error') or 'no code'}")
    tokens = _token({"grant_type": "authorization_code", "client_id": cid, "code": res["code"],
                     "redirect_uri": redirect_uri(), "code_verifier": verifier})
    return tokens


def _token(form):
    data = get_json(TOKEN, data=urllib.parse.urlencode(form).encode(), method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    if "access_token" not in data:
        raise NetError(data.get("error_description") or data.get("error") or "No token from Nexus")
    tokens = {"access_token": data["access_token"], "refresh_token": data.get("refresh_token", ""),
              "expires_at": time.time() + int(data.get("expires_in") or 3600) - 60}
    vault.put_json("oauth", tokens)
    return tokens


_lock = threading.Lock()


def access_token():
    """a current access token (refreshed when it's run out), or "" when not signed in this way"""
    with _lock:
        t = vault.get_json("oauth")
        if not t.get("access_token"):
            return ""
        if time.time() < t.get("expires_at", 0):
            return t["access_token"]
        if not t.get("refresh_token") or not client_id():
            return ""
        try:
            return _token({"grant_type": "refresh_token", "client_id": client_id(),
                           "refresh_token": t["refresh_token"]})["access_token"]
        except NetError as e:
            if e.status in (400, 401):
                vault.put_json("oauth", {})
            raise


def signed_in():
    return bool(vault.get_json("oauth").get("access_token"))


def logout():
    t = vault.get_json("oauth")
    vault.put_json("oauth", {})
    if t.get("refresh_token") and client_id():
        try:
            get_json(REVOKE, data=urllib.parse.urlencode({"token": t["refresh_token"], "client_id": client_id(),
                                                          "token_type_hint": "refresh_token"}).encode(),
                     method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
        except NetError:
            pass


def threading_login(open_url):
    """login() with a way to cancel it from the UI: (run, cancel)"""
    flag = {"stop": False}
    return (lambda: login(open_url, lambda: flag["stop"])), (lambda: flag.__setitem__("stop", True))
