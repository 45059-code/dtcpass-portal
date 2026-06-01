"""
GitHub File Uploader - Pushes files to GitHub without Git installed.
Uses GitHub REST API with a Personal Access Token.

HOW TO GET A TOKEN:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scope: "repo" (full control)
4. Copy the token and paste below
"""

import urllib.request
import urllib.error
import json
import base64
import os

# ─────────────────────────────────────────────
# FILL IN YOUR DETAILS HERE
GITHUB_TOKEN = "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"   # Paste your token
REPO_OWNER   = "45059-code"               # Your GitHub username
REPO_NAME    = "dtcpass-portal"           # Your repo name
BRANCH       = "main"
# ─────────────────────────────────────────────

ROOT = r"D:\dtcpass.delhi.gov.in"

FILES_TO_PUSH = [
    ("backend/requirements.txt",  os.path.join(ROOT, "backend", "requirements.txt")),
    ("backend/api_server.py",     os.path.join(ROOT, "backend", "api_server.py")),
    ("render.yaml",               os.path.join(ROOT, "render.yaml")),
    ("vercel.json",               os.path.join(ROOT, "vercel.json")),
    (".vercelignore",             os.path.join(ROOT, ".vercelignore")),
    ("viewEBPass.html",           os.path.join(ROOT, "viewEBPass.html")),
    ("viewEPass.html",            os.path.join(ROOT, "viewEPass.html")),
    ("registeredUsers.html",      os.path.join(ROOT, "registeredUsers.html")),
    ("getEPass.jsp.html",         os.path.join(ROOT, "getEPass.jsp.html")),
    ("apply.html",                os.path.join(ROOT, "apply.html")),
]

def api_request(method, url, data=None, token=None):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "dtcpass-uploader/1.0"
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return json.loads(error_body) if error_body else {}, e.code

def get_file_sha(path_in_repo):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{path_in_repo}?ref={BRANCH}"
    resp, status = api_request("GET", url, token=GITHUB_TOKEN)
    if status == 200:
        return resp.get("sha")
    return None

def upload_file(local_path, repo_path, commit_message):
    print(f"\n[*] Uploading: {repo_path}")
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    sha = get_file_sha(repo_path)
    if sha:
        print(f"    (updating existing file, sha={sha[:10]}...)")
    else:
        print("    (creating new file)")

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{repo_path}"
    payload = {
        "message": commit_message,
        "content": content,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp, status = api_request("PUT", url, data=payload, token=GITHUB_TOKEN)
    if status in (200, 201):
        print(f"    [OK] Uploaded successfully!")
        return True
    else:
        print(f"    [FAIL] Status {status}: {resp.get('message', resp)}")
        return False

if __name__ == "__main__":
    print("=" * 55)
    print("  DTC e-BusPass - GitHub File Uploader")
    print("=" * 55)

    if GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE":
        print("\n[ERROR] Please edit this script and set your GITHUB_TOKEN!")
        print("  1. Open UPLOAD_TO_GITHUB.py")
        print("  2. Replace YOUR_GITHUB_TOKEN_HERE with your actual token")
        print("  3. Get a token at: https://github.com/settings/tokens")
        input("\nPress Enter to exit...")
        exit(1)

    commit_msg = "fix: support custom profile QR codes and origin-based scanner bypass URL"
    success_count = 0

    for repo_path, local_path in FILES_TO_PUSH:
        if not os.path.exists(local_path):
            print(f"\n[SKIP] File not found: {local_path}")
            continue
        if upload_file(local_path, repo_path, commit_msg):
            success_count += 1

    print("\n" + "=" * 55)
    if success_count == len(FILES_TO_PUSH):
        print(f"  SUCCESS! All {success_count} files pushed to GitHub.")
        print("  Render will auto-redeploy in ~2 minutes.")
        print("  Check: https://dashboard.render.com")
    else:
        print(f"  Done: {success_count}/{len(FILES_TO_PUSH)} files uploaded.")
    print("=" * 55)

