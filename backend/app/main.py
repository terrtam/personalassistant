from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.core.settings import get_settings
from app.routes.health import router as health_router
from app.routes.llm import router as llm_router
from app.routes.notes import router as notes_router

logger = logging.getLogger(__name__)

embeddings_router = None
embeddings_router_import_error = None
try:
    from app.routes.embeddings import router as embeddings_router
except Exception as exc:
    embeddings_router_import_error = exc

settings = get_settings()
app = FastAPI(title="Calendar Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(llm_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
if embeddings_router is not None:
    app.include_router(embeddings_router, prefix="/api")
else:
    logger.warning(
        "Embeddings routes were not loaded: %s", embeddings_router_import_error
    )
