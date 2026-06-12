#!/usr/bin/env python3
"""
Monthly health check for the Instagram Page token.

Exits non-zero if the token no longer works, which makes the GitHub Action fail
and GitHub emails the repo owner. The Page token is non-expiring, so this only
fires if the token is revoked (password change, app change, Meta invalidation).
"""
import os
import sys

import requests

GRAPH = os.environ.get("GRAPH_API_VERSION", "v23.0")
uid = os.environ.get("IG_USER_ID", "").strip()
tok = os.environ.get("IG_PAGE_TOKEN", "").strip()

if not uid or not tok:
    print("Missing IG_USER_ID / IG_PAGE_TOKEN secrets", file=sys.stderr)
    sys.exit(1)

r = requests.get(
    "https://graph.facebook.com/%s/%s" % (GRAPH, uid),
    params={"fields": "username,name", "access_token": tok},
    timeout=30,
)
print(r.status_code, r.text)

ok = r.ok
try:
    if "error" in r.json():
        ok = False
except Exception:
    ok = False

if not ok:
    print("Instagram token check FAILED — regenerate the Page token.", file=sys.stderr)
    sys.exit(1)

print("Instagram token OK.")
