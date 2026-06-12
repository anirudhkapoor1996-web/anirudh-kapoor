#!/usr/bin/env python3
"""AKD Instagram publisher (self-healing). Transient Meta errors are retried on
the next scheduled run without failing the job; only hard errors fail + alert.
One project's failure never blocks the others."""
import os, sys, json, time, glob, pathlib, datetime
import requests
GRAPH = os.environ.get("GRAPH_API_VERSION", "v23.0")
BASE = "https://graph.facebook.com/" + GRAPH
SITE = os.environ.get("SITE_BASE_URL", "https://anirudh-kapoor.com").rstrip("/")
UID = os.environ.get("IG_USER_ID", "").strip()
TOKEN = os.environ.get("IG_PAGE_TOKEN", "").strip()

class TransientError(Exception): pass
class HardError(Exception): pass

if not UID or not TOKEN:
    print("ERROR: IG_USER_ID and IG_PAGE_TOKEN must be set", file=sys.stderr); sys.exit(1)

def _transient(status, j):
    if status >= 500: return True
    e = j.get("error") if isinstance(j, dict) else None
    return bool(e and (e.get("is_transient") or e.get("code") in (1, 2)))

def _req(method, path, **kw):
    last = None
    for attempt in range(4):
        try:
            r = requests.request(method, BASE + "/" + path, timeout=90, **kw)
        except Exception as ex:
            last = str(ex); time.sleep(min(2 ** (attempt + 1), 20)); continue
        j = {}
        try: j = r.json()
        except Exception: pass
        if r.ok and not (isinstance(j, dict) and "error" in j): return j
        last = (r.status_code, j or r.text)
        if _transient(r.status_code, j) and attempt < 3:
            time.sleep(min(2 ** (attempt + 1), 20)); continue
        raise (TransientError if _transient(r.status_code, j) else HardError)("%s %s: %s" % (method, path, last))
    raise TransientError("%s %s after retries: %s" % (method, path, last))

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
    return api_post("%s/media_publish" % UID, {"creation_id": p})["id"]
def publish_reel(ref, m):
    d = {"media_type": "REELS", "video_url": media_url(ref, m["media"][0]), "caption": m.get("caption", "")}
    if m.get("cover"): d["cover_url"] = media_url(ref, m["cover"])
    c = api_post("%s/media" % UID, d)["id"]; wait_ready(c)
    return api_post("%s/media_publish" % UID, {"creation_id": c})["id"]
PUB = {"image": publish_image, "carousel": publish_carousel, "reel": publish_reel}

def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    hard = transient = False; did = 0
    for path in sorted(glob.glob(str(root / "social" / "*" / "post.json"))):
        folder = pathlib.Path(path).parent; ref = folder.name
        if ref.startswith("_") or (folder / ".posted").exists(): continue
        m = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not m.get("ready"): print("skip %s: not ready" % ref); continue
        if m.get("type", "carousel") not in PUB or not m.get("media"):
            print("skip %s: bad manifest" % ref); hard = True; continue
        try:
            print("Publishing %s (%s) -> %d item(s)..." % (ref, m.get("type","carousel"), len(m["media"])))
            mid = PUB[m.get("type", "carousel")](ref, m)
            (folder / ".posted").write_text(json.dumps(
                {"ig_media_id": mid, "posted_at": datetime.datetime.utcnow().isoformat() + "Z",
                 "ref": ref, "type": m.get("type", "carousel")}, indent=2), encoding="utf-8")
            print("PUBLISHED %s -> %s" % (ref, mid)); did += 1
        except TransientError as e:
            print("TRANSIENT (Meta busy; will retry next scheduled run): %s" % e); transient = True
        except HardError as e:
            print("HARD ERROR: %s" % e, file=sys.stderr); hard = True
    if did: print("Posted %d project(s)." % did)
    sys.exit(1 if hard else 0)

if __name__ == "__main__":
    main()
