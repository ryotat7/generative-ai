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

Uploads the rendered demo video into the execution environment's Google Drive folder.
Prioritizes the host execution environment's Google account rather than the demo deployment
tenant, ensuring deliverables are saved to the operator's personal/corp Drive.
Supports native `gdrive` CLI (when available) and Google Drive v3 REST API
with `gcloud auth print-access-token --account=<target_account>`.
Defaults to owner-only private permissions (no public link sharing).
"""

import argparse
import getpass
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
GDRIVE_BIN = "/google/bin/releases/gemini-agents-gdrive/gdrive"


def gdrive_cli_available() -> bool:
    """Checks if internal gdrive CLI is present and executable."""
    return os.path.exists(GDRIVE_BIN) and os.access(GDRIVE_BIN, os.X_OK)


def detect_host_drive_account() -> str:
    """Dynamically detects the host execution environment's Google account without hardcoding.

    Priority:
    1. Explicit environment variable `DRIVE_ACCOUNT`
    2. Non-demo user account matching local host username / LDAP
    3. Corporate user account (@google.com) from `gcloud auth list`
    4. First non-demo human account in `gcloud auth list`
    5. Fallback to active gcloud account
    """
    env_acct = os.environ.get("DRIVE_ACCOUNT", "").strip()
    if env_acct:
        return env_acct

    # Query gcloud credentialed accounts
    accounts = []
    active_acct = ""
    try:
        res = subprocess.run(
            ["gcloud", "auth", "list", "--format=json"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(res.stdout)
        for entry in data:
            acct = entry.get("account", "").strip()
            status = entry.get("status", "")
            if status == "ACTIVE":
                active_acct = acct
            if not acct or "@" not in acct:
                continue
            parts = acct.split("@", 1)[1].lower().split(".")
            if parts[-1] == "com" and len(parts) >= 2 and parts[-2] == "gserviceaccount":
                continue
            accounts.append(acct)
    except Exception:
        pass

    # Filter out known demo tenant and sandbox domains
    non_demo_accounts = []
    for a in accounts:
        parts = a.split("@", 1)[1].lower().split(".")
        if len(parts) >= 2 and parts[-1] == "com" and (parts[-2].startswith("alto") or parts[-2] == "example"):
            continue
        non_demo_accounts.append(a)

    try:
        host_user = getpass.getuser().strip().lower()
    except Exception:
        host_user = ""

    if host_user:
        for a in non_demo_accounts:
            if a.lower().startswith(host_user + "@"):
                return a

    corp_accounts = [a for a in non_demo_accounts if a.lower().endswith("@google.com")]
    if corp_accounts:
        return corp_accounts[0]

    if non_demo_accounts:
        return non_demo_accounts[0]

    if accounts:
        return accounts[0]

    return active_acct or "default"


def drive_access_token(account: str = "") -> str:
    """Retrieves access token from gcloud for a specific account or active account."""
    cmd = ["gcloud", "auth", "print-access-token"]
    if account and account != "default":
        cmd.extend(["--account", account])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        print(f"⚠️ Failed to obtain gcloud access token for account '{account or 'active'}': {e}", file=sys.stderr)
        return ""


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


# ---------------------------------------------------------
# Native gdrive CLI Support (when available)
# ---------------------------------------------------------

def gdrive_find_folder(name: str) -> tuple:
    """Finds an existing folder with the given name using gdrive CLI. Returns (id, web_link)."""
    try:
        res = subprocess.run(
            [GDRIVE_BIN, "readonly", "search", "--name-exact", name, "--json"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(res.stdout)
        for item in data:
            if item.get("mimeType") == "application/vnd.google-apps.folder":
                fid = item.get("id", "")
                link = item.get("webViewLink", f"https://drive.google.com/drive/folders/{fid}")
                return fid, link
    except Exception:
        pass
    return "", ""


def gdrive_create_folder(name: str) -> tuple:
    """Creates a folder using gdrive CLI. Returns (id, web_link)."""
    try:
        res = subprocess.run(
            [GDRIVE_BIN, "mutate", "mkdir", name],
            capture_output=True, text=True, check=True
        )
        out = res.stdout.strip()
        m = re.search(r"\(ID:\s*([a-zA-Z0-9_-]+)\)", out)
        if m:
            fid = m.group(1)
            return fid, f"https://drive.google.com/drive/folders/{fid}"
    except Exception as e:
        print(f"⚠️ Failed to create Drive folder via gdrive CLI: {e}", file=sys.stderr)
    return "", ""


def gdrive_upload_video(video_path: str, parent_id: str = "") -> tuple:
    """Uploads video using gdrive CLI. Returns (id, web_link, err)."""
    try:
        cmd = [GDRIVE_BIN, "mutate", "upload", video_path]
        if parent_id:
            cmd.extend(["--parent", parent_id])
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stdout.strip()
        m = re.search(r"\(ID:\s*([a-zA-Z0-9_-]+)\)", out)
        if m:
            fid = m.group(1)
            return fid, f"https://drive.google.com/file/d/{fid}/view", ""
        return "", "", f"Could not parse file ID from gdrive output: {out}"
    except subprocess.CalledProcessError as e:
        return "", "", f"gdrive upload failed: {e.stderr or e.stdout}"
    except Exception as e:
        return "", "", str(e)


def deliver_video(
    video_path: str,
    company: str,
    role: str,
    suffix: str = "",
    outdir: str = "./deliverables",
    skip_drive: bool = False,
    drive_account: str = "",
    drive_folder: str = "",
    share_public: bool = False
) -> dict:
    """Delivers video to local deliverables and Google Drive.

    Prioritizes the execution environment's Google account rather than the demo deployment tenant.
    Defaults to owner-only private permissions (no public link sharing).
    """
    os.makedirs(outdir, exist_ok=True)
    clean_name = (f"[Demo-Video] {company} - {role}" + (f" ({suffix})" if suffix else "")).replace("/", "-").replace(" ", "_")
    local_dest = os.path.join(outdir, f"{clean_name}.mp4")

    if os.path.abspath(video_path) != os.path.abspath(local_dest):
        shutil.copy2(video_path, local_dest)
        print(f"📁 Local deliverable preserved at: {local_dest}")

    # Resolve target account dynamically without hardcoding
    target_account = drive_account.strip() or detect_host_drive_account()
    target_folder_name = drive_folder.strip() or f"GE Demo - {company}"

    result = {
        "local_path": local_dest,
        "company": company,
        "role": role,
        "folder_name": target_folder_name,
        "file_name": f"{clean_name}.mp4",
        "target_account": target_account,
        "sharing_mode": "public" if share_public else "owner_private",
        "drive_file_id": "",
        "drive_url": "",
        "folder_url": "",
        "upload_status": "pending"
    }

    env_skip = os.environ.get("SKIP_DRIVE_UPLOAD", "").strip().lower() in ("1", "true", "yes")
    if skip_drive or env_skip:
        print("ℹ️ Google Drive upload skipped (SKIP_DRIVE_UPLOAD or --skip-drive).")
        result["upload_status"] = "skipped"
        return result

    print(f"🎯 Target Google Drive Account: {target_account}")
    print(f"📂 Target Folder               : {target_folder_name}")
    print(f"🔒 Sharing Mode                : {'Public Link' if share_public else 'Owner-only Private'}")

    # ---------------------------------------------------------
    # PATH A: Internal Google Environment (via gdrive CLI)
    # ---------------------------------------------------------
    if gdrive_cli_available() and (target_account.endswith("@google.com") or not target_account or target_account == "default"):
        print("🚀 Using native Google Drive CLI engine...")
        folder_id, folder_url = gdrive_find_folder(target_folder_name)
        if not folder_id:
            print(f"Creating Drive folder: '{target_folder_name}'...")
            folder_id, folder_url = gdrive_create_folder(target_folder_name)

        if folder_id:
            result["folder_id"] = folder_id
            result["folder_url"] = folder_url
            print(f"Uploading {os.path.basename(local_dest)} to Google Drive...")
            file_id, web_link, err = gdrive_upload_video(local_dest, parent_id=folder_id)
            if file_id:
                result["drive_file_id"] = file_id
                result["drive_url"] = web_link
                result["upload_status"] = "success"
                if share_public:
                    print("  Enabling public link sharing...")
                    subprocess.run([GDRIVE_BIN, "mutate", "share", file_id, "--type", "anyone", "--role", "reader"], capture_output=True)
                else:
                    print("  🔒 Keeping file permissions private to owner.")
                print(f"  ✅ Uploaded to Google Drive: {web_link}")
                return result
            else:
                print(f"  ⚠️ gdrive CLI upload encountered: {err}. Attempting REST API fallback...", file=sys.stderr)

    # ---------------------------------------------------------
    # PATH B: Standard REST API (via gcloud auth print-access-token)
    # ---------------------------------------------------------
    token = drive_access_token(target_account)
    if not token:
        print("ℹ️ Missing Google Drive access token. Video preserved locally only.")
        print(f"   Run `gcloud auth login --enable-gdrive-access --account={target_account}` to enable Drive uploads.")
        result["upload_status"] = "skipped"
        return result

    test_info, test_status, _ = drive_request(token, "GET", f"{DRIVE_API}/about?fields=user")
    if test_status != 200:
        print(f"⚠️ Drive scope insufficient ({test_status}) for account '{target_account}'. Video saved locally only.")
        print(f"   Run `gcloud auth login --enable-gdrive-access --account={target_account}`.")
        result["upload_status"] = "scope_insufficient"
        return result

    folder_id = drive_find_folder(token, target_folder_name)
    if not folder_id:
        print(f"Creating Drive folder: '{target_folder_name}'...")
        folder_id = drive_create_folder(token, target_folder_name)

    if not folder_id:
        print("⚠️ Could not establish target Drive folder via REST API.", file=sys.stderr)
        return result

    result["folder_id"] = folder_id
    result["folder_url"] = f"https://drive.google.com/drive/folders/{folder_id}"

    print(f"Uploading {os.path.basename(local_dest)} to Google Drive via REST API...")
    file_id, web_link, err = drive_upload_video(token, local_dest, folder_id, f"{clean_name}.mp4")
    if file_id:
        if share_public:
            print("  Enabling public link sharing...")
            enable_link_sharing(token, file_id)
        else:
            print("  🔒 Keeping file permissions private to owner.")
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
    parser.add_argument("--drive-account", default="", help="Target Google Drive account (defaults to execution environment account)")
    parser.add_argument("--drive-folder", default="", help="Google Drive folder name override")
    parser.add_argument("--share-public", action="store_true", help="Enable public link sharing (default: False, owner-only private)")
    parser.add_argument("--skip-drive", action="store_true", help="Skip Google Drive upload (save to ./deliverables/ only)")
    args = parser.parse_args()

    res = deliver_video(
        args.video,
        args.company,
        args.role,
        suffix=args.suffix,
        outdir=args.outdir,
        skip_drive=args.skip_drive,
        drive_account=args.drive_account,
        drive_folder=args.drive_folder,
        share_public=args.share_public,
    )
    print("\n" + "=" * 60)
    print("🎥 Video Delivery Summary")
    print(f"   Local File    : {res['local_path']}")
    print(f"   Target Account: {res.get('target_account', 'N/A')}")
    print(f"   Sharing Mode  : {res.get('sharing_mode', 'N/A')}")
    if res.get("drive_url"):
        print(f"   Drive File    : {res['drive_url']}")
        print(f"   Folder URL    : {res['folder_url']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
