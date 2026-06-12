#!/usr/bin/env python3
"""
AKD Instagram publisher — runs in GitHub Actions.

Scans social/<ref>/post.json for manifests that are marked ready and not yet
posted, and publishes each to Instagram (@anirudh_kapoor_designs) via the
Instagram Graph API. On success it writes social/<ref>/.posted, which the
workflow commits back so the post never goes out twice.

Required env (GitHub Actions secrets):
  IG_USER_ID       Instagram Business account id (e.g. 17841410295912764)
  IG_PAGE_TOKEN    Never-expiring Page access token

Optional env (repo variables):
  SITE_BASE_URL        Public base URL hosting the slides
                       (default: https://anirudh-kapoor.com)
  GRAPH_API_VERSION    default v23.0

post.json shape:
{
  "ref": "A-02",
  "type": "carousel",            # "image" | "carousel" | "reel"
  "ready": true,                  # must be true to publish
  "caption": "Caption text…\n\n#hashtags",
  "media": ["slide-1.jpg", "slide-2.jpg", "slide-3.jpg"],   # reel: ["reel.mp4"]
  "cover": "slide-1.jpg"          # optional, reels only
}

The Instagram API fetches each image/video from its PUBLIC URL, so the slides
must be reachable at  SITE_BASE_URL/social/<ref>/<filename>  over HTTPS.
"""
import os
import sys
import json
import time
import glob
import pathlib
import datetime

import requests

GRAPH = os.environ.get("GRAPH_API_VERSION", "v23.0")
BASE = "https://graph.facebook.com/" + GRAPH
SITE = os.environ.get("SITE_BASE_URL", "https://anirudh-kapoor.com").rstrip("/")
UID = os.environ.get("IG_USER_ID", "").strip()
TOKEN = os.environ.get("IG_PAGE_TOKEN", "").strip()


def die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


if not UID or not TOKEN:
    die("IG_USER_ID and IG_PAGE_TOKEN must be set as repository secrets.")


def api_post(path, data):
    payload = dict(data)
    payload["access_token"] = TOKEN
    r = requests.post(BASE + "/" + path, data=payload, timeout=60)
    j = {}
    try:
        j = r.json()
    except Exception:
        pass
    if not r.ok or "error" in j:
        die("POST %s failed [%s]: %s" % (path, r.status_code, j or r.text))
    return j


def api_get(path, params):
    p = dict(params)
    p["access_token"] = TOKEN
    r = requests.get(BASE + "/" + path, params=p, timeout=60)
    j = {}
    try:
        j = r.json()
    except Exception:
        pass
    if not r.ok or "error" in j:
        die("GET %s failed [%s]: %s" % (path, r.status_code, j or r.text))
    return j


def media_url(ref, filename):
    return "%s/social/%s/%s" % (SITE, ref, filename)


def wait_ready(container_id, tries=30, delay=10):
    """Reels/video must finish processing before they can be published."""
    for _ in range(tries):
        j = api_get(container_id, {"fields": "status_code"})
        sc = j.get("status_code")
        if sc == "FINISHED":
            return
        if sc in ("ERROR", "EXPIRED"):
            die("Container %s processing failed: %s" % (container_id, j))
        time.sleep(delay)
    die("Container %s not ready after waiting." % container_id)


def publish_image(ref, m):
    cont = api_post("%s/media" % UID, {
        "image_url": media_url(ref, m["media"][0]),
        "caption": m.get("caption", ""),
    })["id"]
    return api_post("%s/media_publish" % UID, {"creation_id": cont})["id"]


def publish_carousel(ref, m):
    children = []
    for f in m["media"]:
        c = api_post("%s/media" % UID, {
            "image_url": media_url(ref, f),
            "is_carousel_item": "true",
        })["id"]
        children.append(c)
    parent = api_post("%s/media" % UID, {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": m.get("caption", ""),
    })["id"]
    return api_post("%s/media_publish" % UID, {"creation_id": parent})["id"]


def publish_reel(ref, m):
    data = {
        "media_type": "REELS",
        "video_url": media_url(ref, m["media"][0]),
        "caption": m.get("caption", ""),
    }
    if m.get("cover"):
        data["cover_url"] = media_url(ref, m["cover"])
    cont = api_post("%s/media" % UID, data)["id"]
    wait_ready(cont)
    return api_post("%s/media_publish" % UID, {"creation_id": cont})["id"]


PUBLISHERS = {
    "image": publish_image,
    "carousel": publish_carousel,
    "reel": publish_reel,
}


def main():
    root = pathlib.Path(__file__).resolve().parent.parent  # repo root
    manifests = sorted(glob.glob(str(root / "social" / "*" / "post.json")))
    did = 0
    for path in manifests:
        folder = pathlib.Path(path).parent
        ref = folder.name
        if ref.startswith("_"):          # templates / scratch folders
            continue
        if (folder / ".posted").exists():
            print("skip %s: already posted" % ref)
            continue
        m = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not m.get("ready"):
            print("skip %s: not ready" % ref)
            continue
        typ = m.get("type", "carousel")
        if typ not in PUBLISHERS:
            die("%s: unknown type '%s'" % (ref, typ))
        if not m.get("media"):
            die("%s: no media listed" % ref)
        print("Publishing %s (%s) -> %d item(s)..." % (ref, typ, len(m["media"])))
        media_id = PUBLISHERS[typ](ref, m)
        marker = {
            "ig_media_id": media_id,
            "posted_at": datetime.datetime.utcnow().isoformat() + "Z",
            "ref": ref,
            "type": typ,
        }
        (folder / ".posted").write_text(json.dumps(marker, indent=2), encoding="utf-8")
        print("PUBLISHED %s -> IG media id %s" % (ref, media_id))
        did += 1
    if did == 0:
        print("No ready, unposted manifests found. Nothing to do.")


if __name__ == "__main__":
    main()
