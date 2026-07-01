#!/usr/bin/env python3
"""
AKD Google Drive archival — runs after all social platforms succeed.

For each project in social/<ref>/ that has been posted to ALL required
platforms (IG + FB + LinkedIn), this script:
  1. Uploads all slides to the "AKD — Posted Designs" folder in Google Drive.
  2. Writes social/<ref>/.drive-archived with the Drive folder URL.

Required env (GitHub Actions secrets):
  GOOGLE_SERVICE_ACCOUNT_JSON   JSON key for a Google Service Account
                                 that has Editor access to the Drive folder.

Required env (repo variables or secrets):
  DRIVE_ARCHIVE_FOLDER_ID       Drive folder ID for "AKD — Posted Designs"
                                 (current value: 1vWU62Br4t93mcMENTFxaxlaslAEF6nQ3)
"""
import ast, os, sys, json, glob, pathlib, datetime, mimetypes

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_LIBS = True
except ImportError:
    GOOGLE_LIBS = False

# --- config -------------------------------------------------------------------
REQUIRED_MARKERS = [".posted", ".posted-fb", ".posted-li"]

FOLDER_ID = os.environ.get("DRIVE_ARCHIVE_FOLDER_ID",
                            "1vWU62Br4t93mcMENTFxaxlaslAEF6nQ3")
SA_JSON   = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
SCOPES    = ["https://www.googleapis.com/auth/drive"]
# ------------------------------------------------------------------------------


def die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def parse_service_account_json(raw):
    """
    Parse the service account JSON secret, handling common storage artefacts:
      1. Correct JSON  (ideal)
      2. Double-escaped: literal \\n instead of real newlines — happens when
         someone pastes through a tool that escapes line endings
      3. Python dict repr with single quotes
    """
    if not raw:
        die("GOOGLE_SERVICE_ACCOUNT_JSON secret is not set or is empty.")

    # Attempt 1: standard JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: replace literal \n / \t / \r with real whitespace, then JSON
    try:
        cleaned = (raw
                   .replace('\\n', '\n')
                   .replace('\\t', '\t')
                   .replace('\\r', '\r'))
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Attempt 3: Python dict literal (single-quoted keys/values)
    try:
        result = ast.literal_eval(raw)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    die("GOOGLE_SERVICE_ACCOUNT_JSON could not be parsed after 3 attempts. "
        "First 4 chars: " + repr(raw[:4]) + ". "
        "Please re-paste the raw .json key file content into the GitHub secret.")


def build_drive_service():
    if not GOOGLE_LIBS:
        die("google-api-python-client not installed.")
    info  = parse_service_account_json(SA_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def create_subfolder(service, name, parent_id):
    meta = {
        "name":     name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents":  [parent_id],
    }
    f = service.files().create(body=meta, fields="id,webViewLink").execute()
    return f["id"], f["webViewLink"]


def upload_file(service, local_path, parent_id):
    name    = local_path.name
    mime, _ = mimetypes.guess_type(str(local_path))
    mime    = mime or "application/octet-stream"
    media   = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
    meta    = {"name": name, "parents": [parent_id]}
    f       = service.files().create(body=meta, media_body=media,
                                      fields="id").execute()
    return f["id"]


def all_required_markers_present(folder):
    return all((folder / m).exists() for m in REQUIRED_MARKERS)


def main():
    root      = pathlib.Path(__file__).resolve().parent.parent
    manifests = sorted(glob.glob(str(root / "social" / "*" / "post.json")))

    archivable = []
    for path in manifests:
        folder = pathlib.Path(path).parent
        ref    = folder.name
        if ref.startswith("_"):
            continue
        if (folder / ".drive-archived").exists():
            print("skip %s: already archived to Drive" % ref)
            continue
        if not all_required_markers_present(folder):
            missing = [m for m in REQUIRED_MARKERS if not (folder / m).exists()]
            print("skip %s: missing markers %s" % (ref, missing))
            continue
        m = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not m.get("ready"):
            continue
        archivable.append((ref, folder, m))

    if not archivable:
        print("No projects ready to archive to Drive.")
        return

    service = build_drive_service()

    for ref, folder, m in archivable:
        print("Archiving %s to Google Drive..." % ref)

        title    = m.get("caption", "").split("\n")[0][:60] or ref
        sub_name = "%s -- %s" % (ref, title)
        sub_id, sub_url = create_subfolder(service, sub_name, FOLDER_ID)

        uploaded = []
        for f in sorted(folder.iterdir()):
            if f.name.startswith(".DS_Store"):
                continue
            if f.is_file():
                fid = upload_file(service, f, sub_id)
                uploaded.append(f.name)
                print("  uploaded %s" % f.name)

        record = {
            "drive_folder_id":  sub_id,
            "drive_folder_url": sub_url,
            "archived_at":      datetime.datetime.utcnow().isoformat() + "Z",
            "ref":              ref,
            "files_uploaded":   len(uploaded),
        }
        (folder / ".drive-archived").write_text(
            json.dumps(record, indent=2), encoding="utf-8")
        print("ARCHIVED %s -> Drive: %s" % (ref, sub_url))

    print("Drive archival complete.")


if __name__ == "__main__":
    main()
