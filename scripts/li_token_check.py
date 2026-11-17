#!/usr/bin/env python3
"""Weekly health check for the LinkedIn publishing credential.

Why this exists: the LinkedIn leg of "Social Publish" failed silently from
10 Aug 2026 to 9 Oct 2026 (60 days, runs 246-250) because nothing watched the
token. Instagram has instagram-token-check.yml; LinkedIn had no equivalent.

What it does, deliberately mirroring scripts/li_publish.py:
  * resolves the token exactly the way li_publish.py resolve_token() does, so
    a pass here means the publisher's own credential path works;
  * calls GET /v2/userinfo, which is literally the publisher's first API call
    (person_urn), so this tests the stage that actually fails;
  * exits non-zero on failure, which fails the Action and makes GitHub email
    the repo owner.

It also warns (without failing) when only the static LINKEDIN_ACCESS_TOKEN is
configured, because that token lives ~60 days and will die again. Setting
LINKEDIN_REFRESH_TOKEN + LINKEDIN_CLIENT_SECRET makes li_publish.py mint a
fresh token on every run, with no code change.

Reads secrets only from the environment. Never prints a token.
"""
import os
import sys

import requests

API = 'https://api.linkedin.com'
CID_DEFAULT = '86oymgay2bftr5'


def resolve_token():
    rt = os.environ.get('LINKEDIN_REFRESH_TOKEN', '').strip()
    cs = os.environ.get('LINKEDIN_CLIENT_SECRET', '').strip()
    cid = os.environ.get('LINKEDIN_CLIENT_ID', CID_DEFAULT).strip()
    if rt and cs:
        try:
            r = requests.post(
                'https://www.linkedin.com/oauth/v2/accessToken',
                data={'grant_type': 'refresh_token', 'refresh_token': rt,
                      'client_id': cid, 'client_secret': cs},
                timeout=60)
            if r.ok and r.json().get('access_token'):
                return r.json()['access_token'], 'refresh'
            print('LI: refresh failed (%s %s)' % (r.status_code, r.text[:200]),
                  file=sys.stderr)
        except Exception as ex:
            print('LI: refresh exception (%s)' % ex, file=sys.stderr)
        return os.environ.get('LINKEDIN_ACCESS_TOKEN', '').strip(), 'static-after-refresh-failure'
    return os.environ.get('LINKEDIN_ACCESS_TOKEN', '').strip(), 'static'


def main():
    tok, path = resolve_token()
    print('credential path resolved: %s' % path)
    if not tok:
        print('No usable LinkedIn credential. Set LINKEDIN_REFRESH_TOKEN + '
              'LINKEDIN_CLIENT_SECRET, or LINKEDIN_ACCESS_TOKEN.',
              file=sys.stderr)
        return 1
    try:
        r = requests.get(API + '/v2/userinfo',
                         headers={'Authorization': 'Bearer ' + tok},
                         timeout=60)
    except Exception as ex:
        print('userinfo request failed to complete: %s' % ex, file=sys.stderr)
        return 1
    print('userinfo: %s' % r.status_code)
    if r.status_code >= 500:
        print('LinkedIn returned a server error. Transient, not a token '
              'fault. Not failing the run.', file=sys.stderr)
        return 0
    if not r.ok:
        print('LinkedIn token check FAILED (%s %s). The publish step will '
              'fail too. Regenerate the credential.'
              % (r.status_code, r.text[:300]), file=sys.stderr)
        return 1
    try:
        sub = r.json().get('sub', '')
    except Exception:
        sub = ''
    if not sub:
        print('userinfo returned 200 with no sub field, so person_urn would '
              'fail in li_publish.py.', file=sys.stderr)
        return 1
    print('LinkedIn token OK. urn:li:person:%s' % sub)
    if path.startswith('static'):
        print('WARNING: running on the static LINKEDIN_ACCESS_TOKEN, which '
              'lives about 60 days and will expire silently. Add '
              'LINKEDIN_REFRESH_TOKEN and LINKEDIN_CLIENT_SECRET to make '
              'li_publish.py mint a fresh token every run.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
