#!/usr/bin/env python3
"""
AKD Google Drive archival — runs after all social platforms succeed.

For each project in social/<ref>/ that has been posted to ALL required
platforms (IG + FB + LinkedIn + site), this script:
  1. Uploads all slides to the "AKD — Posted Designs" folder in Google Drive.
  2. Writes social/<ref>/.drive-archived with the Drive folder URL.

Required env (GitHub Actions secrets):
  GOOGLE_SERVICE_ACCOUNT_JSON   JSON key for a Google Service Account
                                 that has Editor access to the Drive folder.

Required env (repo variables or secrets):
  DRIVE_ARCHIVE_FOLDER_ID       Drive folder ID for "AKD — Posted Designs"
                                 (current value: 1vWU62Br4t93mcMENTFxaxlaslAEF6nQ3)

SETUP STEPS (one-time, done in Google Cloud Console):
  1. Create a Service Account in your Google Cloud project.
  2. Grant it "Editor" access to the "AKD — Posted Designs" Drive folder
     (share the folder with the service account's email address).
  3. Create and download a JSON key for the service account.
  4. Add the JSON key as GitHub secret GOOGLE_SERVICE_ACCOUNT_JSON.
  5. Add DRIVE_ARCHIVE_FOLDER_ID = 1vWU62Br4t93mcMENTFxaxlaslAEF6nQ3
     as a GitHub repository variable (or secret).

Required platforms before archiving (can be adjusted below):
  REQUIRED_MARKERS = [".posted", ".posted-fb", ".posted-li"]

Optional (manual platforms -- add marker file manually in the repo to unblock):
  Upwork:  .posted-upwork
  Fiverr:  .posted-fiverr
  Cowork:  .posted-cowork
  (These are NOT required for Drive archival by default, but you can add them
   to REQUIRED_MARKERS once you set up those workflows.)
"""
import os, sys, json, glob, pathlib, datetime, mimetypes

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_LIBS = True
except ImportError:
    GOOGLE_LIBS = False

# --- config -------------------------------------------------------------------
REQUIRED_MARKERS  = [".posted", ".posted-fb", ".posted-li"]
# Add ".posted-upwork", ".posted-fiverr", ".posted-cowork" once those are live.

FOLDER_ID = os.environ.get("DRIVE_ARCHIVE_FOLDER_ID",
                            "1vWU62Br4t93mcMENTFxaxlaslAEF6nQ3")
SA_JSON   = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
SCOPES    = ["https://www.googleapis.com/auth/drive"]
# ------------------------------------------------------------------------------


def die(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def build_drive_service():
    if not GOOGLE_LIBS:
        die("google-api-python-client not installed. Add it to the workflow's pip install.")
    if not SA_JSON:
        die("GOOGLE_SERVICE_ACCOUNT_JSON secret is not set.")
    info  = json.loads(SA_JSON)
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
    name     = local_path.name
    mime, _  = mimetypes.guess_type(str(local_path))
    mime     = mime or "application/octet-stream"
    media    = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
    meta     = {"name": name, "parents": [parent_id]}
    f        = service.files().create(body=meta, media_body=media,
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

        # Create a subfolder named "<ref> -- <title or ref>" inside the archive folder
        title    = m.get("caption", "").split("\n")[0][:60] or ref
        sub_name = "%s -- %s" % (ref, title)
        sub_id, sub_url = create_subfolder(service, sub_name, FOLDER_ID)

        # Upload slides + post.json + all marker files
        uploaded = []
        for f in sorted(folder.iterdir()):
            if f.name.startswith(".DS_Store"):
                continue
            if f.is_file():
                fid = upload_file(service, f, sub_id)
                uploaded.append({"file": f.name, "drive_id": fid})
                print("  uploaded %s" % f.name)

        record = {
            "drive_folder_id":  sub_id,
            "drive_folder_url": sub_url,
            "archived_at":      datetime.datetime.utcnow().isoformat() + "Z",
            "ref":              ref,
            "files_uploaded":   len(uploaded),
        }
        (folder / ".drive-archived").write_text(json.dumps(record, indent=2),
                                                  encoding="utf-8")
        print("ARCHIVED %s -> Drive: %s" % (ref, sub_url))

    print("Drive archival complete.")


if __name__ == "__main__":
    main()
