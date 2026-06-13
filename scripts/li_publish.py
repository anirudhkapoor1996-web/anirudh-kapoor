#!/usr/bin/env python3
"""AKD LinkedIn publisher - ONE post per day to Anirudh's personal profile.

Token handling:
  * If LINKEDIN_REFRESH_TOKEN + LINKEDIN_CLIENT_SECRET are set, the script mints
    a fresh access token from the refresh token on every run (refresh tokens last
    ~12 months) -> hands-off for ~a year.
  * Otherwise it uses LINKEDIN_ACCESS_TOKEN directly (~60-day life).
  * Missing both -> clean no-op (exit 0).
Other secrets: LINKEDIN_CLIENT_ID (default 86oymgay2bftr5), LINKEDIN_VERSION (default 202506).
"""
import os, sys, json, time, glob, pathlib, datetime
import requests

API = "https://api.linkedin.com"
SITE = os.environ.get("SITE_BASE_URL", "https://anirudh-kapoor.com").rstrip("/")
VERSION = os.environ.get("LINKEDIN_VERSION", "202506").strip()
MIN_HOURS = float(os.environ.get("MIN_HOURS_BETWEEN_POSTS", "20"))
MARKER = ".posted-li"
MAX_IMAGES = 9

class TransientError(Exception): pass
class HardError(Exception): pass

def resolve_token():
    """Refresh-token flow if available, else the static access token."""
    rt = os.environ.get("LINKEDIN_REFRESH_TOKEN", "").strip()
    cs = os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip()
    cid = os.environ.get("LINKEDIN_CLIENT_ID", "86oymgay2bftr5").strip()
    if rt and cs:
        try:
            r = requests.post("https://www.linkedin.com/oauth/v2/accessToken",
                              data={"grant_type": "refresh_token", "refresh_token": rt,
                                    "client_id": cid, "client_secret": cs}, timeout=60)
            if r.ok and r.json().get("access_token"):
                print("LI: minted fresh access token from refresh token.")
                return r.json()["access_token"]
            print("LI: refresh failed (%s); falling back to static token." % (r.text[:200]))
        except Exception as ex:
            print("LI: refresh exc (%s); falling back to static token." % ex)
    return os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()

def media_url(ref, fn): return "%s/social/%s/%s" % (SITE, ref, fn)

_RESERVED = "\\<>(){}[]@|~_*#"
def escape_commentary(t):
    out = []
    for ch in t:
        if ch in _RESERVED: out.append("\\")
        out.append(ch)
    return "".join(out)

def _check(r, ctx):
    if r.status_code >= 500:
        raise TransientError("%s: %s %s" % (ctx, r.status_code, r.text[:300]))
    if not r.ok:
        raise HardError("%s: %s %s" % (ctx, r.status_code, r.text[:400]))
    return r

def H(tok): return {"Authorization": "Bearer " + tok, "X-Restli-Protocol-Version": "2.0.0",
                    "LinkedIn-Version": VERSION}

def person_urn(tok):
    r = requests.get(API + "/v2/userinfo", headers={"Authorization": "Bearer " + tok}, timeout=60)
    _check(r, "userinfo")
    return "urn:li:person:" + r.json()["sub"]

def upload_image(tok, owner, img_bytes):
    init = requests.post(API + "/rest/images?action=initializeUpload",
                         headers={**H(tok), "Content-Type": "application/json"},
                         data=json.dumps({"initializeUploadRequest": {"owner": owner}}), timeout=60)
    _check(init, "initializeUpload")
    v = init.json()["value"]
    put = requests.put(v["uploadUrl"], headers={"Authorization": "Bearer " + tok, "Content-Type": "image/jpeg"},
                       data=img_bytes, timeout=120)
    _check(put, "image PUT")
    return v["image"]

def publish(tok, ref, m, owner):
    urns = []
    for fn in m["media"][:MAX_IMAGES]:
        b = requests.get(media_url(ref, fn), timeout=90); _check(b, "download %s" % fn)
        urns.append(upload_image(tok, owner, b.content))
    commentary = escape_commentary(m.get("caption", ""))
    content = ({"media": {"id": urns[0], "altText": ref}} if len(urns) == 1
               else {"multiImage": {"images": [{"id": u, "altText": "%s slide %d" % (ref, i + 1)} for i, u in enumerate(urns)]}})
    body = {"author": owner, "commentary": commentary, "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "content": content, "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    r = requests.post(API + "/rest/posts", headers={**H(tok), "Content-Type": "application/json"},
                      data=json.dumps(body), timeout=90)
    _check(r, "create post")
    return r.headers.get("x-restli-id") or "(posted)"

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
    tok = resolve_token()
    if not tok:
        print("LinkedIn token not set - skipping (no-op)."); return 0
    root = pathlib.Path(__file__).resolve().parent.parent
    h = hours_since_last(root)
    if h is not None and h < MIN_HOURS:
        print("LI: last post %.1fh ago (< %.0fh). Already posted today." % (h, MIN_HOURS)); return 0
    nxt = next_project(root)
    if not nxt:
        print("LI: queue empty - nothing to do."); return 0
    folder, ref, m = nxt
    try:
        owner = person_urn(tok)
        print("LI: publishing %s -> %d image(s) as %s..." % (ref, min(len(m["media"]), MAX_IMAGES), owner))
        pid = publish(tok, ref, m, owner)
        (folder / MARKER).write_text(json.dumps(
            {"li_post_id": pid, "posted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "ref": ref}, indent=2),
            encoding="utf-8")
        print("LI PUBLISHED %s -> %s" % (ref, pid)); return 0
    except TransientError as e:
        print("LI transient - try next daily run.\n  %s" % e); return 0
    except HardError as e:
        print("LI HARD ERROR %s: %s" % (ref, e), file=sys.stderr); return 1

if __name__ == "__main__":
    sys.exit(main())
