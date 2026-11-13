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


class NetError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


def request(url, data=None, headers=None, method=None, timeout=30):
    check_url(url)
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
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw, dict(r.headers)
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
    if not url.lower().startswith("https://") and not url.lower().startswith("http://"):
        raise NetError(f"Not a web address: {url[:80]}")


def download(url, dest, progress=None, cancelled=lambda: False, headers=None):
    """download to dest (through dest.part); progress(done, total) every chunk"""
    check_url(url)
    h = {"User-Agent": UA}
    h.update(headers or {})
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as f:
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
        return url if os.path.isfile(url) else None
    if not url.lower().startswith(("https://", "http://")):
        return None
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1][:5] or ".img"
    path = os.path.join(CACHE, "img", hashlib.sha1(url.encode()).hexdigest() + ext)
    if os.path.isfile(path):
        return path
    try:
        raw, _ = request(url, timeout=20)
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
