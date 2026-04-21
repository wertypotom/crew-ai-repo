import os
import tempfile
import subprocess
from fastapi import FastAPI, Request
from api_evolution_crew.main import run_repo_audit
from github import Github, GithubIntegration, Auth
import httpx

async def post_to_dashboard(audit_payload: dict):
    try:
        async with httpx.AsyncClient() as client:
            await client.post("http://localhost:3000/api/audits", json=audit_payload)
    except Exception as e:
        print(f"Dashboard update failed (non-critical): {e}")
        
app = FastAPI()

@app.post("/webhook")
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
    
    print(f"🚀 Received Webhook: {repo_full_name} PR #{pr_number}")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"📥 Shallow cloning {head_branch} into ephemeral directory {temp_dir}...")
        
        # Clone ONLY the latest commit of the affected branch to map the blast radius
        subprocess.run([
            "git", "clone", "--depth=1", "-b", head_branch, clone_url, temp_dir
        ], check=True)
        
        print("⚙️ Preparing ephemeral repository (installing backend deps & building static docs)...")
        server_path = os.path.join(temp_dir, "server")
        if os.path.exists(server_path):
            subprocess.run(["npm", "install"], cwd=server_path, check=True)
            subprocess.run(["npm", "run", "generate:docs"], cwd=server_path, check=True)
        
        print(f"🧠 Kicking off AI Architecture Audit...")
        
        # Execute the CrewAI logic in a separate thread!
        # This is critical because FastAPI runs an active event loop, and CrewAI tools use `asyncio.run()`.
        # Offloading it to a thread ensures the Agent doesn't crash from asyncio loop collisions.
        import asyncio
        report_markdown = await asyncio.to_thread(run_repo_audit, temp_dir, base_branch)
        print(f"✅ Audit Complete! Markdown length: {len(report_markdown)}")
        
        # Log into GitHub using App Authentication to post securely as a Bot!
        app_id = os.environ.get("GITHUB_APP_ID")
        pem_path = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")
        
        if app_id and pem_path and os.path.exists(pem_path):
            try:
                with open(pem_path, 'r') as f:
                    private_key = f.read()
                
                # Securely authenticate as the overarching App
                auth = Auth.AppAuth(app_id, private_key)
                gi = GithubIntegration(auth=auth)
                
                # Fetch the short-lived installation ID specifically tied to the repository that triggered this webhook
                installation_id = payload.get("installation", {}).get("id")
                if not installation_id:
                    print("⚠️ Webhook is missing 'installation' payload. Make sure the App is installed on this repository!")
                else:
                    g = gi.get_github_for_installation(installation_id)
                    repo = g.get_repo(repo_full_name)
                    pr = repo.get_pull(pr_number)
                    
                    # Create the automated comment!
                    pr.create_issue_comment(f"## 🤖 API Evolution Audit\n\n{report_markdown}")
                    print("💬 Successfully posted Drift Report comment as the App Bot!")
                    
                    # ADDING A DASHBOARD POSTING STEP
                    await post_to_dashboard({
                        "prNumber":    pr_number,
                        "prTitle":     payload["pull_request"]["title"],
                        "branch":      head_branch,
                        "repo":        repo_full_name,
                        "status":      "breaking" if "BREAKING" in report_markdown else
                                    "warning"  if "WARNING"  in report_markdown else "clean",
                        "driftReport": [],
                        "blastRadius": [],
                        "log": [
                            f"PR #{pr_number} opened",
                            "Repo cloned to ephemeral dir",
                            "npm install + generate:docs done",
                            "drift_analyzer started",
                            "blast_radius_mapper started",
                            f"Report posted to PR #{pr_number}"
                        ]
                    })
            except Exception as e:
                print(f"❌ Failed to post to GitHub via App Auth: {e}")
        else:
            print("⚠️ GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY_PATH not configured properly. Will not post to PR.")

    return {"status": "Processed", "repo": repo_full_name, "pr": pr_number}
