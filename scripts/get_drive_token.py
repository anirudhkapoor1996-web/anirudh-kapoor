#!/usr/bin/env python3
"""
One-time helper: exchange a Google OAuth2 authorization code for a
refresh token that can be stored as a GitHub Actions secret.

Run this ONCE locally:
    pip install google-auth-oauthlib
    python scripts/get_drive_token.py

Then store the printed values as GitHub secrets:
    GOOGLE_OAUTH_CLIENT_ID
    GOOGLE_OAUTH_CLIENT_SECRET
    GOOGLE_OAUTH_REFRESH_TOKEN

Steps BEFORE running:
  1. Go to https://console.cloud.google.com/apis/credentials
     (project: maximal-beach-409712)
  2. Click "Create Credentials" -> "OAuth client ID"
  3. Application type: Desktop app
     Name: AKD Drive Archiver
  4. Click Create, then "Download JSON"
  5. Paste the client_id and client_secret below (or pass as env vars)
"""
import os, json, webbrowser

CLIENT_ID     = os.environ.get("GOOGLE_OAUTH_CLIENT_ID",     "YOUR_CLIENT_ID_HERE")
CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
SCOPES        = ["https://www.googleapis.com/auth/drive"]
REDIRECT_URI  = "urn:ietf:wg:oauth:2.0:oob"   # copy-paste flow, no local server needed

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Run: pip install google-auth-oauthlib")
    raise

if CLIENT_ID == "YOUR_CLIENT_ID_HERE":
    print("Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET env vars first.")
    raise SystemExit(1)

# Build a minimal client config
client_config = {
    "installed": {
        "client_id":                CLIENT_ID,
        "client_secret":            CLIENT_SECRET,
        "redirect_uris":            [REDIRECT_URI],
        "auth_uri":                 "https://accounts.google.com/o/oauth2/auth",
        "token_uri":                "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== COPY THESE INTO GITHUB SECRETS ===")
print("GOOGLE_OAUTH_CLIENT_ID     =", CLIENT_ID)
print("GOOGLE_OAUTH_CLIENT_SECRET =", CLIENT_SECRET)
print("GOOGLE_OAUTH_REFRESH_TOKEN =", creds.refresh_token)
print("=======================================")
print("\nDone. Add the 3 values above to:")
print("https://github.com/anirudhkapoor1996-web/anirudh-kapoor/settings/secrets/actions")
