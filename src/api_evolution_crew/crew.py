from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from api_evolution_crew.tools import (
    get_git_diff, read_source_file, database_introspector, 
    get_dependency_graph, read_openapi_route
)

@CrewBase
class ApiEvolutionCrew():
    """ApiEvolutionCrew crew"""

    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @agent
    def drift_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config['drift_analyzer'],
            tools=[get_git_diff, read_source_file, database_introspector, read_openapi_route],
            step_callback=getattr(self, 'custom_step_callback', None),
            verbose=True,
            max_iter=5
        )

    @agent
    def blast_radius_mapper(self) -> Agent:
        return Agent(
            config=self.agents_config['blast_radius_mapper'],
            tools=[get_dependency_graph, read_source_file],
            step_callback=getattr(self, 'custom_step_callback', None),
            verbose=True
        )

    @task
    def audit_api_drift_task(self) -> Task:
        return Task(
            config=self.tasks_config['audit_api_drift_task'],
        )

    @task
    def map_frontend_impact_task(self) -> Task:
        return Task(
            config=self.tasks_config['map_frontend_impact_task'],
            context=[self.audit_api_drift_task()]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the ApiEvolutionCrew crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            step_callback=getattr(self, 'custom_step_callback', None),
            verbose=True,
            tracing=True,
        )
