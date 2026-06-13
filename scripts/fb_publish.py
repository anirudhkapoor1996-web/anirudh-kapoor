#!/usr/bin/env python3
"""AKD Facebook Page publisher - ONE post per day.

Mirrors the Instagram queue (social/<ref>/post.json) to the Facebook Page as a
multi-photo post. Independent of Instagram: its own per-platform marker
(.posted-fb) and its own 20h guard, so FB drains the same archive order at one
post/day without being blocked by IG's rate limits.

Secrets (GitHub repo -> Settings -> Secrets and variables -> Actions):
  FB_PAGE_TOKEN  - Page access token with pages_manage_posts (never-expiring)
  FB_PAGE_ID     - the Facebook Page id (defaults to the AKD Designs page)
If FB_PAGE_TOKEN is absent the script is a clean no-op (exit 0), so it is safe to
wire into the workflow before the token exists.
"""
import os, sys, json, time, glob, pathlib, datetime
import requests

GRAPH = os.environ.get("GRAPH_API_VERSION", "v23.0")
BASE = "https://graph.facebook.com/" + GRAPH
SITE = os.environ.get("SITE_BASE_URL", "https://anirudh-kapoor.com").rstrip("/")
TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()
PAGE_ID = os.environ.get("FB_PAGE_ID", "1163349337160596").strip()
MIN_HOURS = float(os.environ.get("MIN_HOURS_BETWEEN_POSTS", "20"))
MARKER = ".posted-fb"

class TransientError(Exception): pass
class RateLimited(Exception): pass
class HardError(Exception): pass

def _classify(status, j):
    e = j.get("error") if isinstance(j, dict) else None
    if e:
        if e.get("code") in (4, 17, 32, 613) or e.get("is_transient"):
            return "rate" if e.get("code") in (4, 17, 32, 613) else "transient"
    if status >= 500:
        return "transient"
    return "hard"

def _req(method, path, **kw):
    last = None
    for attempt in range(2):
        try:
            r = requests.request(method, BASE + "/" + path, timeout=90, **kw)
        except Exception as ex:
            last = str(ex); time.sleep(5); continue
        j = {}
        try: j = r.json()
        except Exception: pass
        if r.ok and not (isinstance(j, dict) and "error" in j):
            return j
        kind = _classify(r.status_code, j); last = (r.status_code, j or r.text)
        if kind == "rate": raise RateLimited("%s %s: %s" % (method, path, last))
        if kind == "transient" and attempt == 0: time.sleep(6); continue
        raise (TransientError if kind == "transient" else HardError)("%s %s: %s" % (method, path, last))
    raise TransientError("%s %s after retry: %s" % (method, path, last))

def media_url(ref, fn): return "%s/social/%s/%s" % (SITE, ref, fn)

def resolve_page_token(tok):
    """Accept either a User token (with pages_manage_posts) or a Page token and
    return a proper PAGE token. Posting unpublished photos must be done as the
    page itself, so a user token alone yields error #200. GET /{page}?fields=
    access_token with a user token returns the page token; with a page token it
    returns itself. Falls back to the given token if the lookup fails."""
    try:
        r = requests.get(BASE + "/" + PAGE_ID, params={"fields": "access_token", "access_token": tok}, timeout=60)
        j = r.json()
        if r.ok and isinstance(j, dict) and j.get("access_token"):
            return j["access_token"]
        print("FB: page-token lookup returned no token (%s); using provided token as-is." % (j.get("error", {}).get("message") if isinstance(j, dict) else r.status_code))
    except Exception as ex:
        print("FB: page-token lookup failed (%s); using provided token as-is." % ex)
    return tok

def publish(ref, m, page_token):
    """Unpublished photo per slide, then a single feed post with all of them."""
    fbids = []
    for fn in m["media"]:
        r = _req("POST", "%s/photos" % PAGE_ID,
                 data={"url": media_url(ref, fn), "published": "false", "access_token": page_token})
        fbids.append(r["id"])
    data = {"message": m.get("caption", ""), "access_token": page_token}
    for i, fb in enumerate(fbids):
        data["attached_media[%d]" % i] = json.dumps({"media_fbid": fb})
    return _req("POST", "%s/feed" % PAGE_ID, data=data)["id"]

def hours_since_last(root):
    newest = None
    for p in glob.glob(str(root / "social" / "*" / MARKER)):
        try:
            ts = json.loads(pathlib.Path(p).read_text(encoding="utf-8")).get("posted_at", "")
            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if newest is None or dt > newest: newest = dt
        except Exception: continue
    if newest is None: return None
    return (datetime.datetime.now(datetime.timezone.utc) - newest).total_seconds() / 3600.0

def next_project(root):
    for path in sorted(glob.glob(str(root / "social" / "*" / "post.json"))):
        folder = pathlib.Path(path).parent; ref = folder.name
        if ref.startswith("_") or (folder / MARKER).exists(): continue
        m = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not m.get("ready") or not m.get("media"): continue
        return folder, ref, m
    return None

def main():
    if not TOKEN:
        print("FB_PAGE_TOKEN not set - skipping Facebook (no-op)."); return 0
    root = pathlib.Path(__file__).resolve().parent.parent
    h = hours_since_last(root)
    if h is not None and h < MIN_HOURS:
        print("FB: last post %.1fh ago (< %.0fh). Already posted today." % (h, MIN_HOURS)); return 0
    nxt = next_project(root)
    if not nxt:
        print("FB: queue empty - nothing to do."); return 0
    folder, ref, m = nxt
    try:
        page_token = resolve_page_token(TOKEN)
        print("FB: publishing %s -> %d photo(s)..." % (ref, len(m["media"])))
        pid = publish(ref, m, page_token)
        (folder / MARKER).write_text(json.dumps(
            {"fb_post_id": pid, "posted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "ref": ref}, indent=2),
            encoding="utf-8")
        print("FB PUBLISHED %s -> %s" % (ref, pid)); return 0
    except RateLimited as e:
        print("FB rate limited - try next daily run.\n  %s" % e); return 0
    except TransientError as e:
        print("FB transient - try next daily run.\n  %s" % e); return 0
    except HardError as e:
        print("FB HARD ERROR %s: %s" % (ref, e), file=sys.stderr); return 1

if __name__ == "__main__":
    sys.exit(main())
