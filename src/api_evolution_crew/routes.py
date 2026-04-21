import os
import tempfile
import subprocess
import urllib.request
import json
import asyncio
from fastapi import APIRouter, Request, BackgroundTasks
from api_evolution_crew.main import run_repo_audit
from github import Github, GithubIntegration, Auth

router = APIRouter()

pr_locks = {}

def notify_dashboard(data):
    try:
        req = urllib.request.Request("http://localhost:3000/api/audits", method="POST")
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, data=json.dumps(data).encode('utf-8'), timeout=2)
    except Exception as e:
        print(f"⚠️ Failed to notify dashboard: {e}")

import re
import sys

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

class DashboardLogCatcher:
    def __init__(self, pr_number, original_stdout):
        self.pr_number = pr_number
        self.original_stdout = original_stdout
        self.buffer = ""

    def write(self, text):
        # Always output to the real console so the user still sees it
        self.original_stdout.write(text)
        self.original_stdout.flush()
        
        # Send the entire chunk as a single log item so multi-line ASCII art isn't broken
        clean_text = ansi_escape.sub('', text).strip('\r\n')
        if clean_text:
            notify_dashboard({"prNumber": self.pr_number, "log": [clean_text]})

    def flush(self):
        self.original_stdout.flush()

async def run_audit_task(payload, repo_full_name, clone_url, pr_number, head_branch, base_branch, head_sha, pr_url, pr_title):
    if pr_number not in pr_locks:
        pr_locks[pr_number] = asyncio.Lock()
        
    async with pr_locks[pr_number]:
        # Notify dashboard that we are starting, clearing old logs
        notify_dashboard({
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
                subprocess.run(["npm", "install"], cwd=server_path, check=True)
                subprocess.run(["npm", "run", "generate:docs"], cwd=server_path, check=True)
            
            # Intercept stdout to capture 100% of verbose CrewAI logs
            original_stdout = sys.stdout
            catcher = DashboardLogCatcher(pr_number, original_stdout)
            
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
                "prNumber": pr_number,
                "status": "breaking" if has_critical else "clean",
                "log": ["✅ Audit Complete!"],
                "finalReport": report_markdown
            })
            
            # Log into GitHub using App Authentication to post securely as a Bot!
            app_id = os.environ.get("GITHUB_APP_ID")
            pem_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
            
            if app_id and pem_path and os.path.exists(pem_path):
                try:
                    with open(pem_path, 'r') as f:
                        private_key = f.read()
                    auth = Auth.AppAuth(app_id, private_key)
                    gi = GithubIntegration(auth=auth)
                    
                    installation_id = payload.get("installation", {}).get("id")
                    if installation_id:
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
    
    print(f"🚀 Received Webhook: {repo_full_name} PR #{pr_number} - Queued for background processing.")
    
    background_tasks.add_task(
        run_audit_task, payload, repo_full_name, clone_url, pr_number, head_branch, base_branch, head_sha, pr_url, pr_title
    )
    
    return {"status": "Queued", "repo": repo_full_name, "pr": pr_number}
