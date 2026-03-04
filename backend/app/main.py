from fastapi import FastAPI
from app.routes.health import router as health_router

app = FastAPI(title="Calendar Agent API")

app.include_router(health_router, prefix="/api")
