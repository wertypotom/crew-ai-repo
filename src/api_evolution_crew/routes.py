import os
import tempfile
import subprocess
import urllib.request
import json
import asyncio
from fastapi import APIRouter, Request
from api_evolution_crew.main import run_repo_audit
from github import Github, GithubIntegration, Auth

router = APIRouter()

def notify_dashboard(data):
    try:
        req = urllib.request.Request("http://localhost:3000/api/audits", method="POST")
        req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(req, data=json.dumps(data).encode('utf-8'), timeout=2)
    except Exception as e:
        print(f"⚠️ Failed to notify dashboard: {e}")

def create_agent_callback(pr_number):
    def step_callback(step):
        # Safely extract thought or tool from CrewAI step
        msg = "🤖 Agent is thinking..."
        if hasattr(step, 'thought') and step.thought:
            msg = f"💭 Thought: {step.thought}"
        elif hasattr(step, 'tool') and step.tool:
            msg = f"🔧 Using Tool: {step.tool} ({step.tool_input})"
        elif isinstance(step, tuple) and len(step) > 0 and hasattr(step[0], 'thought'):
            msg = f"💭 {step[0].thought}"
        else:
            msg = f"🤖 Agent Action: {str(step)[:150]}..."
            
        notify_dashboard({
            "prNumber": pr_number,
            "log": [msg]
        })
    return step_callback

@router.post("/webhook")
async def github_webhook(request: Request):
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
    
    print(f"🚀 Received Webhook: {repo_full_name} PR #{pr_number}")
    
    # Notify dashboard that we are starting
    notify_dashboard({
        "prNumber": pr_number,
        "prTitle": pr_title,
        "branch": head_branch,
        "repo": repo_full_name,
        "status": "pending",
        "prUrl": pr_url,
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
        
        # Execute the CrewAI logic with our step_callback
        callback = create_agent_callback(pr_number)
        report_markdown = await asyncio.to_thread(run_repo_audit, temp_dir, base_branch, callback)
        print(f"✅ Audit Complete! Markdown length: {len(report_markdown)}")
        
        # Pre-calculate critical status for dashboard and github
        upper_report = report_markdown.upper()
        has_critical = "[CRITICAL]" in upper_report or "CRITICAL:" in upper_report or "🚨" in report_markdown
        
        # Notify dashboard that we are done
        notify_dashboard({
            "prNumber": pr_number,
            "status": "breaking" if has_critical else "clean",
            "log": ["✅ Audit Complete!", f"Critical Issues Found: {has_critical}"] + report_markdown.split('\n')
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

    return {"status": "Processed", "repo": repo_full_name, "pr": pr_number}
