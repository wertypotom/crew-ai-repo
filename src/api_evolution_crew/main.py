#!/usr/bin/env python
import os
import sys
import warnings
from dotenv import load_dotenv

load_dotenv()

from api_evolution_crew.crew import ApiEvolutionCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydantic")

def run_repo_audit(target_dir: str, base_branch: str, step_callback=None) -> str:
    """
    Run the crew dynamically on a specified directory and base branch.
    """
    inputs = {
        'target_path': target_dir,
        'base_branch': base_branch
    }
    
    crew_builder = ApiEvolutionCrew()
    
    # Inject the dashboard streaming callback
    if step_callback:
        crew_builder.custom_step_callback = step_callback
            
    # Execute the crew and return the textual markdown output
    output = crew_builder.crew().kickoff(inputs=inputs)
    return str(output.raw if hasattr(output, 'raw') else output)


