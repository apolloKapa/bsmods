"""HTTP with the standard library: JSON requests, downloads with progress, and an image cache."""
import gzip
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import VERSION
from .config import CACHE

UA = f"Armory/{VERSION} (Linux mod manager)"

# the AppImage's OpenSSL looks for certificates where its build machine keeps them (/usr/lib/ssl),
# which most distros don't have: use the system's own bundle, wherever this distro keeps it
CA_FILES = ["/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
            "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem", "/etc/ssl/ca-bundle.pem", "/etc/ssl/cert.pem",
            "/usr/local/share/certs/ca-root-nss.crt", "/etc/certs/ca-certificates.crt"]
_ctx = None


def ssl_context():
    global _ctx
    if _ctx is None:
        import ssl
        cafile = os.environ.get("SSL_CERT_FILE") if os.path.isfile(os.environ.get("SSL_CERT_FILE", "")) else None
        cafile = cafile or next((p for p in CA_FILES if os.path.isfile(p)), None)
        _ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    return _ctx


class NetError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


SENSITIVE = ("apikey", "authorization", "cookie")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """redirects never carry your Nexus key (or a token) to another site, and never go from https
    to plain http (urllib copies every header across redirects by itself)"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = quote_url(newurl)
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if old.scheme == "https" and new.scheme != "https":
            raise urllib.error.HTTPError(newurl, code, "Refused a redirect from https to http", headers, fp)
        out = super().redirect_request(req, fp, code, msg, headers, newurl)
        if out is not None and (old.scheme, old.hostname, old.port) != (new.scheme, new.hostname, new.port):
            for k in list(out.headers):
                if k.lower() in SENSITIVE:
                    del out.headers[k]
            for k in list(out.unredirected_hdrs):
                if k.lower() in SENSITIVE:
                    del out.unredirected_hdrs[k]
        return out


_opener = None


def opener():
    global _opener
    if _opener is None:
        _opener = urllib.request.build_opener(SafeRedirect, urllib.request.HTTPSHandler(context=ssl_context()))
    return _opener


def read_capped(r, limit):
    """the body, refusing anything over limit bytes (also once unzipped)"""
    import zlib
    gz = r.headers.get("Content-Encoding") == "gzip"
    d = zlib.decompressobj(16 + zlib.MAX_WBITS) if gz else None
    out, raw_total = [], 0
    while True:
        chunk = r.read(1 << 16)
        if not chunk:
            break
        raw_total += len(chunk)
        if d is not None:
            chunk = d.decompress(chunk, limit + 1 - sum(map(len, out)))
        out.append(chunk)
        if sum(map(len, out)) > limit or raw_total > limit:
            raise NetError(f"The answer was bigger than {limit // (1 << 20)} MB, so it was refused")
    body = b"".join(out)
    if d is None and body[:2] == b"\x1f\x8b":
        # gzipped without saying so (Thunderstore's listing chunks)
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        body = d.decompress(body, limit + 1)
        if len(body) > limit or d.unconsumed_tail:
            raise NetError(f"The answer was bigger than {limit // (1 << 20)} MB, so it was refused")
    return body


def request(url, data=None, headers=None, method=None, timeout=30, limit=128 << 20):
    url = check_url(url)
    h = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    h.update(headers or {})
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode()
            h.setdefault("Content-Type", "application/json")
        elif isinstance(data, str):
            body = data.encode()
        else:
            body = data
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with opener().open(req, timeout=timeout) as r:
            return read_capped(r, limit), dict(r.headers)
    except urllib.error.HTTPError as e:
        text = ""
        try:
            raw = e.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            text = raw.decode("utf-8", "replace")
            msg = json.loads(text).get("message") or text
        except (ValueError, AttributeError, OSError):
            msg = text or e.reason
        raise NetError(f"{e.code}: {str(msg)[:300]}", e.code) from None
    except (urllib.error.URLError, OSError) as e:
        raise NetError(f"Couldn't connect ({getattr(e, 'reason', e)})") from None


def get_json(url, **kw):
    raw, _ = request(url, **kw)
    try:
        return json.loads(raw)
    except ValueError:
        raise NetError("The server sent something that isn't JSON") from None


def check_url(url):
    """the address, made safe to send: Nexus's file links keep the file's name as it is (spaces and
    all), which urllib refuses, so anything that isn't allowed in a URL is percent-encoded"""
    if not url.lower().startswith("https://") and not url.lower().startswith("http://"):
        raise NetError(f"Not a web address: {url[:80]}")
    return quote_url(url)


def quote_url(url):
    p = urllib.parse.urlsplit(url.strip())
    keep = "/%:@!$&'()*+,;=~-._"
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path, safe=keep),
                                    urllib.parse.quote(p.query, safe=keep + "?"),
                                    urllib.parse.quote(p.fragment, safe=keep + "?")))


def download(url, dest, progress=None, cancelled=lambda: False, headers=None):
    """download to dest (through dest.part); progress(done, total) every chunk"""
    url = check_url(url)
    h = {"User-Agent": UA}
    h.update(headers or {})
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=h)
    try:
        with opener().open(req, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancelled():
                    raise NetError("Cancelled")
                chunk = r.read(1 << 17)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        os.replace(part, dest)
        return dest
    except urllib.error.HTTPError as e:
        raise NetError(f"Download failed: {e.code} {e.reason}", e.code) from None
    except (urllib.error.URLError, OSError) as e:
        if isinstance(e, NetError):
            raise
        raise NetError(f"Download failed ({getattr(e, 'reason', e)})") from None
    finally:
        if os.path.exists(part):
            try:
                os.unlink(part)
            except OSError:
                pass


def cached_image(url):
    """the local file for an image URL, downloading it once"""
    if not url:
        return None
    if os.path.isabs(url):
        # a mod site's data can't point Armory at your own files
        from .config import DATA
        ok = os.path.realpath(url).startswith((os.path.realpath(DATA) + os.sep, os.path.realpath(CACHE) + os.sep))
        return url if ok and os.path.isfile(url) else None
    if not url.lower().startswith(("https://", "http://")):
        return None
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1][:5] or ".img"
    path = os.path.join(CACHE, "img", hashlib.sha1(url.encode()).hexdigest() + ext)
    if os.path.isfile(path):
        return path
    try:
        raw, _ = request(url, timeout=20, limit=15 << 20)
    except NetError:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)
    return path


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
