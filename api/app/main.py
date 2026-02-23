from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import auth, sites, telemetry, audits, incidents, notifications, e911, actions, devices

app = FastAPI(title="TRUE911 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,          prefix="/api/auth",      tags=["auth"])
app.include_router(sites.router,         prefix="/api/sites",     tags=["sites"])
app.include_router(telemetry.router,     prefix="/api/telemetry", tags=["telemetry"])
app.include_router(audits.router,        prefix="/api/audits",    tags=["audits"])
app.include_router(incidents.router,     prefix="/api/incidents", tags=["incidents"])
app.include_router(notifications.router, prefix="/api")
app.include_router(e911.router,          prefix="/api")
app.include_router(actions.router,       prefix="/api")
app.include_router(devices.router,      prefix="/api/devices", tags=["devices"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "app_mode": settings.APP_MODE}
