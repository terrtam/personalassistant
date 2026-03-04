from fastapi import FastAPI
from app.routes.health import router as health_router
from app.routes.llm import router as llm_router

app = FastAPI(title="Calendar Agent API")

app.include_router(health_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
