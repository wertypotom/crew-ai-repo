import os
from crewai import Agent, Task, Crew, Process

# Force tracing env var
os.environ['CREWAI_TRACING'] = 'true'

def test_tracing():
    agent = Agent(
        role='Tester',
        goal='Test tracing',
        backstory='Expert in debugging',
        verbose=True
    )
    
    task = Task(description='Say hello', expected_output='A greeting', agent=agent)
    
    crew = Crew(
        agents=[agent],
        tasks=[task],
        verbose=True,
        tracing=True
    )
    
    print("Starting crew with tracing enabled...")
    result = crew.kickoff()
    print("Run completed.")

if __name__ == "__main__":
    test_tracing()
