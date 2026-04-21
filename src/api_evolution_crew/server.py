from fastapi import FastAPI
from api_evolution_crew.routes import router

app = FastAPI(title="API Evolution Engine", description="GitHub App Webhook Server for CrewAI")
app.include_router(router)
