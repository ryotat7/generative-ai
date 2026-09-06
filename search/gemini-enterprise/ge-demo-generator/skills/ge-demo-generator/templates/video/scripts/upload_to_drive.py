#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Google Drive Uploader for GE Demo Highlight Reel Videos.

Uploads the rendered demo video into the demo's Google Drive folder using the
Google Drive v3 REST API with the active account's access token (`gcloud auth print-access-token`).
Reuses existing folders/files idempotently, enables reader link sharing, and saves a copy
to `./deliverables/`.
"""

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


def drive_access_token() -> str:
    """Retrieves access token from gcloud."""
    try:
        res = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=True
        )
        return res.stdout.strip()
    except Exception as e:
        print(f"⚠️ Failed to obtain gcloud access token: {e}", file=sys.stderr)
        return ""


def get_active_account() -> str:
    """Retrieves active account from gcloud."""
    try:
        res = subprocess.run(
            ["gcloud", "config", "get-value", "account"],
            capture_output=True, text=True, check=True
        )
        return res.stdout.strip()
    except Exception:
        return "Unknown"


def drive_request(token: str, method: str, url: str, headers: dict = None,
                  content_type: str = "application/json; charset=UTF-8", raw: bytes = None):
    """Executes an authenticated Google Drive v3 REST API call."""
    req_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=raw, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            body = json.loads(data.decode("utf-8")) if data else {}
            return body, resp.status, ""
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return {}, e.code, err_body
    except Exception as e:
        return {}, 0, str(e)


def drive_find_folder(token: str, name: str) -> str:
    """Finds an existing folder with the given name owned by the current user."""
    safe_name = name.replace("'", "\\'")
    q = (f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' "
         "and trashed = false and 'me' in owners")
    url = f"{DRIVE_API}/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)"})
    info, status, _ = drive_request(token, "GET", url)
    files = info.get("files") or []
    return files[0].get("id", "") if status == 200 and files else ""


def drive_create_folder(token: str, name: str) -> str:
    """Creates a new folder in Google Drive."""
    body = json.dumps({
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }).encode("utf-8")
    info, status, err = drive_request(token, "POST", f"{DRIVE_API}/files?fields=id", raw=body)
    if status == 200 and info.get("id"):
        return info["id"]
    print(f"⚠️ Failed to create Drive folder: {err}", file=sys.stderr)
    return ""


def drive_find_child(token: str, name: str, parent_id: str) -> str:
    """Finds an existing file with the given name inside parent_id."""
    safe_name = name.replace("'", "\\'")
    q = f"name = '{safe_name}' and '{parent_id}' in parents and trashed = false"
    url = f"{DRIVE_API}/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id)"})
    info, status, _ = drive_request(token, "GET", url)
    files = info.get("files") or []
    return files[0].get("id", "") if status == 200 and files else ""


def drive_upload_video(token: str, video_path: str, parent_id: str, dest_name: str) -> tuple:
    """Uploads a video file into parent_id via multipart/related request."""
    existing_id = drive_find_child(token, dest_name, parent_id)
    metadata = {"name": dest_name}
    if parent_id and not existing_id:
        metadata["parents"] = [parent_id]

    mime = mimetypes.guess_type(video_path)[0] or "video/mp4"
    boundary = "ge-demo-video-boundary"

    with open(video_path, "rb") as fh:
        content = fh.read()

    body = b"".join([
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("utf-8"),
        json.dumps(metadata).encode("utf-8"),
        f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8"),
        content,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ])

    if existing_id:
        method = "PATCH"
        url = f"{DRIVE_UPLOAD_API}/files/{existing_id}?uploadType=multipart&fields=id,webViewLink"
    else:
        method = "POST"
        url = f"{DRIVE_UPLOAD_API}/files?uploadType=multipart&fields=id,webViewLink"

    info, status, err = drive_request(
        token, method, url,
        content_type=f"multipart/related; boundary={boundary}", raw=body
    )
    if status == 200 and info.get("id"):
        web_link = info.get("webViewLink", f"https://drive.google.com/file/d/{info['id']}/view")
        return info["id"], web_link, ""
    return "", "", f"Upload failed ({status}): {err}"


def enable_link_sharing(token: str, file_id: str):
    """Enables 'Anyone with link can view' permission."""
    url = f"{DRIVE_API}/files/{file_id}/permissions"
    body = json.dumps({"role": "reader", "type": "anyone"}).encode("utf-8")
    drive_request(token, "POST", url, raw=body)


def deliver_video(video_path: str, company: str, role: str, suffix: str = "", outdir: str = "./deliverables", skip_drive: bool = False) -> dict:
    """Delivers video to local deliverables and Google Drive."""
    os.makedirs(outdir, exist_ok=True)
    clean_name = f"[Demo-Video] {company} - {role}".replace("/", "-").replace(" ", "_")
    local_dest = os.path.join(outdir, f"{clean_name}.mp4")

    if os.path.abspath(video_path) != os.path.abspath(local_dest):
        shutil.copy2(video_path, local_dest)
        print(f"📁 Local deliverable preserved at: {local_dest}")

    # Check Drive upload
    env_skip = os.environ.get("SKIP_DRIVE_UPLOAD", "").strip().lower() in ("1", "true", "yes")
    should_skip = skip_drive or env_skip
    token = "" if should_skip else drive_access_token()

    result = {
        "local_path": local_dest,
        "company": company,
        "role": role,
        "folder_name": f"GE Demo - {company}" + (f" ({suffix})" if suffix else ""),
        "file_name": f"{clean_name}.mp4",
        "drive_file_id": "",
        "drive_url": "",
        "folder_url": "",
        "upload_status": "skipped" if should_skip else "pending"
    }

    if not token or should_skip:
        print("ℹ️ Google Drive upload skipped (SKIP_DRIVE_UPLOAD or missing access token).")
        print("   Run `gcloud auth login --enable-gdrive-access --no-launch-browser` to enable Drive uploads.")
        return result

    # Check token validity / Drive scope
    test_info, test_status, _ = drive_request(token, "GET", f"{DRIVE_API}/about?fields=user")
    if test_status != 200:
        print(f"⚠️ Drive scope insufficient ({test_status}). Video saved locally only.")
        print("   Run `gcloud auth login --enable-gdrive-access --no-launch-browser`.")
        result["upload_status"] = "scope_insufficient"
        return result

    # Find or create folder
    folder_name = result["folder_name"]
    folder_id = drive_find_folder(token, folder_name)
    if not folder_id:
        print(f"Creating Drive folder: '{folder_name}'...")
        folder_id = drive_create_folder(token, folder_name)
        if folder_id:
            enable_link_sharing(token, folder_id)

    if not folder_id:
        print("⚠️ Could not establish target Drive folder.", file=sys.stderr)
        return result

    result["folder_id"] = folder_id
    result["folder_url"] = f"https://drive.google.com/drive/folders/{folder_id}"

    # Upload video
    print(f"Uploading {os.path.basename(local_dest)} to Google Drive...")
    file_id, web_link, err = drive_upload_video(token, local_dest, folder_id, f"{clean_name}.mp4")
    if file_id:
        enable_link_sharing(token, file_id)
        result["drive_file_id"] = file_id
        result["drive_url"] = web_link
        result["upload_status"] = "success"
        print(f"  ✅ Uploaded to Google Drive: {web_link}")
    else:
        print(f"  ❌ Drive upload failed: {err}", file=sys.stderr)
        result["upload_status"] = "failed"
        result["error"] = err

    return result


def main():
    parser = argparse.ArgumentParser(description="Deliver demo video to Google Drive.")
    parser.add_argument("--video", required=True, help="Path to rendered MP4 video")
    parser.add_argument("--company", default="Enterprise", help="Company name")
    parser.add_argument("--role", default="Operations Director", help="Agent role")
    parser.add_argument("--suffix", default="", help="Demo suffix if any")
    parser.add_argument("--outdir", default="./deliverables", help="Local directory for deliverables")
    parser.add_argument("--skip-drive", action="store_true", help="Skip Google Drive upload (save to ./deliverables/ only)")
    args = parser.parse_args()

    res = deliver_video(args.video, args.company, args.role, args.suffix, args.outdir, skip_drive=args.skip_drive)
    print("\n" + "=" * 60)
    print("🎥 Video Delivery Summary")
    print(f"   Local File : {res['local_path']}")
    if res.get("drive_url"):
        print(f"   Drive File : {res['drive_url']}")
        print(f"   Folder URL : {res['folder_url']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
