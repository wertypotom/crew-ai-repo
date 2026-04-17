# CrewAI Educational Project: Research & Content Crew

This project is a boilerplate designed to help you understand the core logic of **CrewAI**. It demonstrates how to use multiple AI agents to collaborate on a single goal.

## 🚀 How to Run

1.  **Create & Activate Virtual Environment**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
2.  **Install CrewAI**:
    ```bash
    pip install crewai python-dotenv
    ```
3.  **Set your API Key**:
    Open the `.env` file and replace `YOUR_API_KEY_HERE` with your OpenAI API key.
4.  **Run the Crew**:
    ```bash
    export PYTHONPATH=$PYTHONPATH:$(pwd)/src
    python src/educational_crew/main.py
    ```

## 🧠 Core Components Explained

### 1. Agents (`config/agents.yaml`)
Agents are the "workers" in your crew. Each agent has:
- **Role**: What they do (e.g., "Research Specialist").
- **Goal**: What they are trying to achieve.
- **Backstory**: Their personality and expertise, which helps the LLM understand how to behave.

### 2. Tasks (`config/tasks.yaml`)
Tasks are the "assignments" given to agents. A task defines:
- **Description**: What needs to be done.
- **Expected Output**: What the result should look like.
- **Agent**: Which agent is responsible for this task.
- **Context**: (Optional) Which previous tasks this task depends on.

### 3. The Crew (`src/educational_crew/crew.py`)
The Crew is the orchestrator. It brings together the agents and tasks.
- **Process**: Defines how tasks are executed. `Process.sequential` means one after the other. `Process.hierarchical` involves a manager agent.
- **@CrewBase**: This decorator is a CrewAI utility that automatically links your YAML configurations to your Python classes.

### 4. Entry Point (`src/educational_crew/main.py`)
This is where the magic starts.
- **Inputs**: You can pass dynamic variables (like `{topic}`) to your agents and tasks here.
- **kickoff()**: This method starts the execution of the crew.

## 🛠️ Logic Flow
1.  **Input**: You provide a `topic` (e.g., "AI Agents").
2.  **Research**: The `researcher` agent starts the `research_task`, gathering data.
3.  **Handoff**: Once the research is done, the output is passed to the `writer`.
4.  **Writing**: The `writer` agent uses the research results to fulfill the `writing_task`.
5.  **Output**: The final article is generated and saved to `article.md`.
