from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import auth, sites, telemetry, audits, incidents, notifications, e911, actions

app = FastAPI(title="TRUE911 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(sites.router, prefix="/api")
app.include_router(telemetry.router, prefix="/api")
app.include_router(audits.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(e911.router, prefix="/api")
app.include_router(actions.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
