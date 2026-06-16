#!/usr/bin/env python3
"""AKD Instagram publisher - ONE post per day.

Why one-per-day: Instagram's Content Publishing API caps how many media
containers an account may create per rolling 24h. A carousel = (N slides + 1)
containers. Attempting many projects, with retries, on every push blew that cap
(error code 9 / subcode 2207069 "Media creation limit exceeded") and locked the
account out. So publish AT MOST ONE project per run, once a day.

A 20h guard means even if the workflow fires more than once a day we still post
at most once per ~day. Rate-limit (code 9) and transient (5xx / is_transient)
errors are NOT failures - we stop and try again next daily run. Only genuine
config/manifest problems fail the job (and alert).
"""
import os, sys, json, time, glob, pathlib, datetime, re
import requests

GRAPH = os.environ.get("GRAPH_API_VERSION", "v23.0")
BASE = "https://graph.facebook.com/" + GRAPH
SITE = os.environ.get("SITE_BASE_URL", "https://anirudh-kapoor.com").rstrip("/")
UID = os.environ.get("IG_USER_ID", "").strip()
TOKEN = os.environ.get("IG_PAGE_TOKEN", "").strip()
MIN_HOURS = float(os.environ.get("MIN_HOURS_BETWEEN_POSTS", "20"))

class TransientError(Exception): pass
class RateLimited(Exception): pass
class HardError(Exception): pass

if not UID or not TOKEN:
    print("ERROR: IG_USER_ID and IG_PAGE_TOKEN must be set", file=sys.stderr); sys.exit(1)

def _classify(status, j):
    e = j.get("error") if isinstance(j, dict) else None
    if e:
        if e.get("code") in (4, 9) or e.get("error_subcode") in (2207042, 2207051, 2207069):
            return "rate"
        if e.get("is_transient"):
            return "transient"
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
        kind = _classify(r.status_code, j)
        last = (r.status_code, j or r.text)
        if kind == "rate":
            raise RateLimited("%s %s: %s" % (method, path, last))
        if kind == "transient" and attempt == 0:
            time.sleep(6); continue
        raise (TransientError if kind == "transient" else HardError)("%s %s: %s" % (method, path, last))
    raise TransientError("%s %s after retry: %s" % (method, path, last))

def api_post(path, data):
    d = dict(data); d["access_token"] = TOKEN; return _req("POST", path, data=d)
def api_get(path, params):
    p = dict(params); p["access_token"] = TOKEN; return _req("GET", path, params=p)
def media_url(ref, fn): return "%s/social/%s/%s" % (SITE, ref, fn)

def wait_ready(cid, tries=30, delay=10):
    for _ in range(tries):
        sc = api_get(cid, {"fields": "status_code"}).get("status_code")
        if sc == "FINISHED": return
        if sc in ("ERROR", "EXPIRED"): raise HardError("container %s failed" % cid)
        time.sleep(delay)
    raise TransientError("container %s not ready" % cid)

def publish_image(ref, m):
    c = api_post("%s/media" % UID, {"image_url": media_url(ref, m["media"][0]), "caption": m.get("caption", "")})["id"]
    return api_post("%s/media_publish" % UID, {"creation_id": c})["id"]
def publish_carousel(ref, m):
    kids = [api_post("%s/media" % UID, {"image_url": media_url(ref, fn), "is_carousel_item": "true"})["id"] for fn in m["media"]]
    p = api_post("%s/media" % UID, {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": m.get("caption", "")})["id"]
    wait_ready(p)
    return api_post("%s/media_publish" % UID, {"creation_id": p})["id"]
def publish_reel(ref, m):
    d = {"media_type": "REELS", "video_url": media_url(ref, m["media"][0]), "caption": m.get("caption", "")}
    if m.get("cover"): d["cover_url"] = media_url(ref, m["cover"])
    c = api_post("%s/media" % UID, d)["id"]; wait_ready(c)
    return api_post("%s/media_publish" % UID, {"creation_id": c})["id"]
PUB = {"image": publish_image, "carousel": publish_carousel, "reel": publish_reel}

def hours_since_last_post(root):
    newest = None
    for p in glob.glob(str(root / "social" / "*" / ".posted")):
        try:
            ts = json.loads(pathlib.Path(p).read_text(encoding="utf-8")).get("posted_at", "")
            dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if newest is None or dt > newest: newest = dt
        except Exception:
            continue
    if newest is None: return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - newest).total_seconds() / 3600.0

def live_posted_refs():
    """Refs already live on the IG account, read from each post's caption ("... A\u00b7NN.").
    This makes dedup robust even if a .posted marker was lost: we never repost what's already up.
    Best-effort: on any API error we return an empty set and fall back to the .posted markers."""
    refs = set(); after = None
    try:
        for _ in range(6):  # up to ~600 recent posts
            params = {"fields": "caption", "limit": "100"}
            if after: params["after"] = after
            j = api_get("%s/media" % UID, params)
            for it in j.get("data", []):
                cap = it.get("caption") or ""
                for n in re.findall(r"A[\u00b7.\-](\d{1,3})\b", cap):
                    refs.add("A-%02d" % int(n))
            after = ((j.get("paging", {}) or {}).get("cursors", {}) or {}).get("after")
            if not after: break
    except Exception as e:
        print("Live-account dedup unavailable (%s); using .posted markers only." % e, file=sys.stderr)
    return refs

def next_project(root, skip=frozenset()):
    for path in sorted(glob.glob(str(root / "social" / "*" / "post.json"))):
        folder = pathlib.Path(path).parent; ref = folder.name
        if ref.startswith("_") or (folder / ".posted").exists() or ref in skip:
            continue
        m = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not m.get("ready"):
            continue
        if m.get("type", "carousel") not in PUB or not m.get("media"):
            print("skip %s: bad manifest" % ref, file=sys.stderr); continue
        return folder, ref, m
    return None

def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    h = hours_since_last_post(root)
    if h is not None and h < MIN_HOURS:
        print("Last post was %.1fh ago (< %.0fh). Already posted today; nothing to do." % (h, MIN_HOURS))
        return 0
    live = live_posted_refs()
    if live:
        print("Already on the account (will skip): %s" % ", ".join(sorted(live)))
    nxt = next_project(root, skip=live)
    if not nxt:
        print("No ready, un-posted projects in the queue. Nothing to do.")
        return 0
    folder, ref, m = nxt
    typ = m.get("type", "carousel")
    try:
        print("Publishing %s (%s) -> %d item(s)..." % (ref, typ, len(m["media"])))
        mid = PUB[typ](ref, m)
        (folder / ".posted").write_text(json.dumps(
            {"ig_media_id": mid, "posted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "ref": ref, "type": typ}, indent=2), encoding="utf-8")
        print("PUBLISHED %s -> %s  (next project goes out on the next daily run)" % (ref, mid))
        return 0
    except RateLimited as e:
        print("RATE LIMITED by Instagram's 24h creation cap - will try again next daily run.\n  %s" % e)
        return 0
    except TransientError as e:
        print("TRANSIENT (Meta busy) - will try again next daily run.\n  %s" % e)
        return 0
    except HardError as e:
        print("HARD ERROR publishing %s: %s" % (ref, e), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
