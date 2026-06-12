#!/usr/bin/env python3
"""
AKD Instagram publisher — runs in GitHub Actions.
Scans social/<ref>/post.json for ready, un-posted manifests and publishes each
to Instagram (@anirudh_kapoor_designs). Writes social/<ref>/.posted on success.

Resilient to Meta's transient errors (OAuthException code 1/2, is_transient,
5xx) via exponential backoff.
"""
import os, sys, json, time, glob, pathlib, datetime
import requests

GRAPH = os.environ.get("GRAPH_API_VERSION", "v23.0")
BASE = "https://graph.facebook.com/" + GRAPH
SITE = os.environ.get("SITE_BASE_URL", "https://anirudh-kapoor.com").rstrip("/")
UID = os.environ.get("IG_USER_ID", "").strip()
TOKEN = os.environ.get("IG_PAGE_TOKEN", "").strip()

def die(msg):
    print("ERROR: " + msg, file=sys.stderr); sys.exit(1)

if not UID or not TOKEN:
    die("IG_USER_ID and IG_PAGE_TOKEN must be set as repository secrets.")

def _is_transient(status, j):
    if status >= 500:
        return True
    e = j.get("error") if isinstance(j, dict) else None
    if e and (e.get("is_transient") or e.get("code") in (1, 2)):
        return True
    return False

def _req(method, path, **kw):
    url = BASE + "/" + path
    last = None
    for attempt in range(6):
        try:
            r = requests.request(method, url, timeout=90, **kw)
        except Exception as ex:
            last = ("exception", str(ex))
            time.sleep(min(2 ** (attempt + 1), 30)); continue
        j = {}
        try: j = r.json()
        except Exception: pass
        if r.ok and not (isinstance(j, dict) and "error" in j):
            return j
        last = (r.status_code, j or r.text)
        if _is_transient(r.status_code, j) and attempt < 5:
            wait = min(2 ** (attempt + 1), 30)
            print("transient error on %s (attempt %d), retrying in %ds: %s"
                  % (path, attempt + 1, wait, j or r.text))
            time.sleep(wait); continue
        die("%s %s failed [%s]: %s" % (method, path, r.status_code, j or r.text))
    die("%s %s failed after retries: %s" % (method, path, last))

def api_post(path, data):
    d = dict(data); d["access_token"] = TOKEN
    return _req("POST", path, data=d)

def api_get(path, params):
    p = dict(params); p["access_token"] = TOKEN
    return _req("GET", path, params=p)

def media_url(ref, filename):
    return "%s/social/%s/%s" % (SITE, ref, filename)

def wait_ready(container_id, tries=30, delay=10):
    for _ in range(tries):
        sc = api_get(container_id, {"fields": "status_code"}).get("status_code")
        if sc == "FINISHED": return
        if sc in ("ERROR", "EXPIRED"): die("Container %s failed" % container_id)
        time.sleep(delay)
    die("Container %s not ready after waiting." % container_id)

def publish_image(ref, m):
    c = api_post("%s/media" % UID, {"image_url": media_url(ref, m["media"][0]),
                                    "caption": m.get("caption", "")})["id"]
    return api_post("%s/media_publish" % UID, {"creation_id": c})["id"]

def publish_carousel(ref, m):
    kids = []
    for fn in m["media"]:
        kids.append(api_post("%s/media" % UID, {"image_url": media_url(ref, fn),
                                                "is_carousel_item": "true"})["id"])
    parent = api_post("%s/media" % UID, {"media_type": "CAROUSEL",
                                         "children": ",".join(kids),
                                         "caption": m.get("caption", "")})["id"]
    return api_post("%s/media_publish" % UID, {"creation_id": parent})["id"]

def publish_reel(ref, m):
    data = {"media_type": "REELS", "video_url": media_url(ref, m["media"][0]),
            "caption": m.get("caption", "")}
    if m.get("cover"): data["cover_url"] = media_url(ref, m["cover"])
    c = api_post("%s/media" % UID, data)["id"]
    wait_ready(c)
    return api_post("%s/media_publish" % UID, {"creation_id": c})["id"]

PUBLISHERS = {"image": publish_image, "carousel": publish_carousel, "reel": publish_reel}

def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    did = 0
    for path in sorted(glob.glob(str(root / "social" / "*" / "post.json"))):
        folder = pathlib.Path(path).parent; ref = folder.name
        if ref.startswith("_") or (folder / ".posted").exists():
            continue
        m = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not m.get("ready"):
            print("skip %s: not ready" % ref); continue
        typ = m.get("type", "carousel")
        if typ not in PUBLISHERS: die("%s: unknown type '%s'" % (ref, typ))
        if not m.get("media"): die("%s: no media listed" % ref)
        print("Publishing %s (%s) -> %d item(s)..." % (ref, typ, len(m["media"])))
        mid = PUBLISHERS[typ](ref, m)
        (folder / ".posted").write_text(json.dumps(
            {"ig_media_id": mid, "posted_at": datetime.datetime.utcnow().isoformat() + "Z",
             "ref": ref, "type": typ}, indent=2), encoding="utf-8")
        print("PUBLISHED %s -> IG media id %s" % (ref, mid)); did += 1
    if did == 0:
        print("No ready, unposted manifests found.")

if __name__ == "__main__":
    main()
