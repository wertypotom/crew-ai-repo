import os
import tempfile
import subprocess
import urllib.request
import json
import asyncio
import uuid
from fastapi import APIRouter, Request, BackgroundTasks
from api_evolution_crew.main import run_repo_audit
from github import Github, GithubIntegration, Auth

router = APIRouter()

pr_locks = {}
processed_shas = set()

@router.get("/ping")
async def ping():
    """Keep-alive endpoint for Render."""
    return {"status": "alive"}

def notify_dashboard(data):
    dashboard_url = os.environ.get("DASHBOARD_URL", "http://localhost:3000").rstrip("/")
    try:
        req = urllib.request.Request(f"{dashboard_url}/api/audits", method="POST")
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, data=json.dumps(data).encode('utf-8'), timeout=5)
    except Exception as e:
        print(f"⚠️ Failed to notify dashboard at {dashboard_url}: {e}")

import re
import sys

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class DashboardLogCatcher:
    def __init__(self, pr_number, run_id, original_stdout):
        self.pr_number = pr_number
        self.run_id = run_id
        self.original_stdout = original_stdout
        self.buffer = ""

    def write(self, text):
        # Always output to the real console so the user still sees it
        self.original_stdout.write(text)
        self.original_stdout.flush()
        
        # Send the entire chunk as a single log item so multi-line ASCII art isn't broken
        clean_text = ansi_escape.sub('', text).strip('\r\n')
        if clean_text:
            notify_dashboard({"runId": self.run_id, "prNumber": self.pr_number, "log": [clean_text]})

    def flush(self):
        self.original_stdout.flush()

async def run_audit_task(payload, repo_full_name, clone_url, pr_number, head_branch, base_branch, head_sha, pr_url, pr_title, run_id):
    if pr_number not in pr_locks:
        pr_locks[pr_number] = asyncio.Lock()
        
    async with pr_locks[pr_number]:
        # Notify dashboard that we are starting, clearing old logs
        notify_dashboard({
            "runId": run_id,
            "prNumber": pr_number,
            "prTitle": pr_title,
            "branch": head_branch,
            "repo": repo_full_name,
            "status": "pending",
            "prUrl": pr_url,
            "clearLog": True,
            "log": [f"🚀 Webhook received for PR #{pr_number}", f"📥 Cloning branch {head_branch}...", "🧠 Kicking off AI Architecture Audit..."]
        })
        
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"📥 Shallow cloning {head_branch} into ephemeral directory {temp_dir}...")
            subprocess.run(["git", "clone", "--depth=1", "-b", head_branch, clone_url, temp_dir], check=True)
            
            print("⚙️ Preparing ephemeral repository...")
            server_path = os.path.join(temp_dir, "server")
            if os.path.exists(server_path):
                print("📦 Installing server deps (npm ci)...")
                subprocess.run(
                    ["npm", "ci", "--prefer-offline", "--no-audit", "--no-fund"],
                    cwd=server_path, check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                subprocess.run(["npm", "run", "generate:docs"], cwd=server_path, check=True)
            
            client_path = os.path.join(temp_dir, "client")
            if os.path.exists(client_path):
                print("📦 Installing client deps (npm ci)...")
                subprocess.run(
                    ["npm", "ci", "--prefer-offline", "--no-audit", "--no-fund"],
                    cwd=client_path, check=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                subprocess.run(["npm", "run", "generate:api"], cwd=client_path, check=True)
                print("✅ client/src/api/types.d.ts regenerated from current openapi.json")

            
            # Intercept stdout to capture 100% of verbose CrewAI logs
            original_stdout = sys.stdout
            catcher = DashboardLogCatcher(pr_number, run_id, original_stdout)
            
            try:
                sys.stdout = catcher
                # Execute the CrewAI logic
                report_markdown = await asyncio.to_thread(run_repo_audit, temp_dir, base_branch)
            finally:
                sys.stdout = original_stdout
                
            print(f"✅ Audit Complete! Markdown length: {len(report_markdown)}")
            
            # Pre-calculate critical status for dashboard and github
            upper_report = report_markdown.upper()
            has_critical = "[CRITICAL]" in upper_report or "CRITICAL:" in upper_report or "🚨" in report_markdown
            
            # Notify dashboard that we are done
            notify_dashboard({
                "runId": run_id,
                "prNumber": pr_number,
                "status": "breaking" if has_critical else "clean",
                "log": ["✅ Audit Complete!"],
                "finalReport": report_markdown
            })
            
            # Log into GitHub using App Authentication to post securely as a Bot!
            app_id = (os.environ.get("GITHUB_APP_ID") or "").strip().strip('"').strip("'")
            
            # Support both: raw key content via env var (Cloud Run) or file path (local/Render)
            private_key = (os.environ.get("GITHUB_APP_PRIVATE_KEY") or "").strip()
            if not private_key:
                pem_path = (os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH") or "").strip().strip('"').strip("'")
                if pem_path and os.path.exists(pem_path):
                    with open(pem_path, 'r') as f:
                        private_key = f.read()
            
            if app_id and private_key:
                try:
                    auth = Auth.AppAuth(app_id, private_key)

                    gi = GithubIntegration(auth=auth)
                    
                    installation_id = payload.get("installation", {}).get("id")
                    if installation_id:
                        installation_id = int(installation_id)
                        g = gi.get_github_for_installation(installation_id)
                        repo = g.get_repo(repo_full_name)
                        pr = repo.get_pull(pr_number)
                        
                        pr.create_issue_comment(f"## 🤖 API Evolution Audit\n\n{report_markdown}")
                        print("💬 Successfully posted Drift Report comment as the App Bot!")
                        
                        status_state = "failure" if has_critical else "success"
                        status_desc = "Critical Architecture Drifts Detected!" if has_critical else "Architecture is aligned."
                        
                        head_commit = repo.get_commit(head_sha)
                        head_commit.create_status(
                            state=status_state,
                            description=status_desc,
                            context="API Evolution Audit"
                        )
                        print(f"🔒 Set GitHub Commit Status to: {status_state}")
                except Exception as e:
                    print(f"❌ Failed to post to GitHub via App Auth: {e}")
            else:
                print("⚠️ GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY_PATH not configured properly.")

@router.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    
    # Only react to Pull Requests
    if "pull_request" not in payload:
        return {"status": "Ignored - not a pull request event"}
        
    action = payload.get("action")
    if action not in ["opened", "synchronize", "reopened"]:
        return {"status": f"Ignored - PR action {action} is not targeted"}
        
    repo_full_name = payload["repository"]["full_name"]
    clone_url = payload["repository"]["clone_url"]
    pr_number = payload["pull_request"]["number"]
    
    head_branch = payload["pull_request"]["head"]["ref"]
    base_branch = payload["pull_request"]["base"]["ref"]
    head_sha = payload["pull_request"]["head"]["sha"]
    pr_url = payload["pull_request"]["html_url"]
    pr_title = payload["pull_request"]["title"]
    
    # Ignore webhooks without an installation ID. 
    # GitHub Apps send a "good" webhook with this ID; raw repo webhooks don't.
    # Ignoring the "bad" one prevents double-execution.
    installation_id = payload.get("installation", {}).get("id")
    if not installation_id:
        print(f"⏭️ Ignoring webhook for PR #{pr_number} - No GitHub App installation ID (likely a redundant repo webhook).")
        return {"status": "Ignored - no installation ID"}

    if head_sha in processed_shas:
        print(f"⏭️ Skipping duplicate webhook for PR #{pr_number} - SHA {head_sha[:7]} already queued.")
        return {"status": "Ignored - commit already processed"}
    
    processed_shas.add(head_sha)
    
    run_id = str(uuid.uuid4())
    
    background_tasks.add_task(
        run_audit_task, payload, repo_full_name, clone_url, pr_number, head_branch, base_branch, head_sha, pr_url, pr_title, run_id
    )
    
    return {"status": "Queued", "repo": repo_full_name, "pr": pr_number}
