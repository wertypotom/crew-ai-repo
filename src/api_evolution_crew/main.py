#!/usr/bin/env python
import os
import sys
import warnings
from dotenv import load_dotenv

load_dotenv()

from crewai import Crew
from api_evolution_crew.crew import ApiEvolutionCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydantic")

def run_repo_audit(target_dir: str, base_branch: str, step_callback=None) -> str:
    """
    Run the crew with 'Fast-Fail' logic: 
    1. Run Drift Audit.
    2. If [DRIFT_DETECTED] found, STOP and return report.
    3. If clean, proceed to Frontend Impact analysis.
    """
    inputs = {
        'target_path': target_dir,
        'base_branch': base_branch
    }
    
    crew_builder = ApiEvolutionCrew()
    
    # STEP 1: Run the Drift Audit Task
    print("🔍 Step 1: Running Architecture Drift Audit...")
    drift_crew = Crew(
        agents=[crew_builder.drift_analyzer()],
        tasks=[crew_builder.audit_api_drift_task()],
        verbose=True
    )
    drift_result = drift_crew.kickoff(inputs=inputs)
    drift_report = str(drift_result.raw if hasattr(drift_result, 'raw') else drift_result)
    
    # STEP 2: Fast-Fail & Remediation Check
    if "[DRIFT_DETECTED]" in drift_report:
        print("🚨 DRIFT DETECTED: Running Remediation Step...")
        remediation_crew = Crew(
            agents=[crew_builder.architecture_fixer()],
            tasks=[crew_builder.suggest_remediation_task()],
            verbose=True
        )
        # Pass the drift report as context for the fixer
        inputs['drift_report'] = drift_report
        remediation_result = remediation_crew.kickoff(inputs=inputs)
        remediation_plan = str(remediation_result.raw if hasattr(remediation_result, 'raw') else remediation_result)
        
        print("🛑 Short-circuiting execution. Returning Drift Report + Remediation Plan.")
        return f"{drift_report}\n\n## 🛠️ Proposed Remediation Plan\n\n{remediation_plan}"
        
    # STEP 3: If clean, run the Frontend Impact Task
    print("✅ No core drift detected. Step 2: Mapping Frontend Impact...")
    impact_crew = Crew(
        agents=[crew_builder.blast_radius_mapper()],
        tasks=[crew_builder.map_frontend_impact_task()],
        verbose=True
    )
    inputs['drift_report'] = drift_report
    impact_result = impact_crew.kickoff(inputs=inputs)
    impact_report = str(impact_result.raw if hasattr(impact_result, 'raw') else impact_result)
    
    # STEP 4: Auto-fix broken frontend files
    print("🔧 Step 3: Applying Frontend Code Fixes...")
    fix_crew = Crew(
        agents=[crew_builder.frontend_code_fixer()],
        tasks=[crew_builder.apply_frontend_fixes_task()],
        verbose=True
    )
    inputs['impact_report'] = impact_report
    fix_result = fix_crew.kickoff(inputs=inputs)
    fix_summary = str(fix_result.raw if hasattr(fix_result, 'raw') else fix_result)

    # Return both the human-readable impact report AND the machine-parseable fix summary
    # routes.py looks for [FIXED_FILES] to decide whether to git commit + push
    return f"{impact_report}\n\n---\n{fix_summary}"


