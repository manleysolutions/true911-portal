from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import auth, sites, telemetry, audits, incidents, notifications, e911, actions, devices

app = FastAPI(title="TRUE911 API", version="1.0.0")

# CORS — wildcard origins and allow_credentials=True are mutually exclusive
# per the Fetch spec.  Browsers silently reject the response when both are set.
# When CORS_ORIGINS is ["*"] we must set allow_credentials=False.
_allow_creds = not settings.cors_is_wildcard

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=_allow_creds,
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


@app.get("/api/debug/cors")
async def debug_cors():
    """Return resolved CORS config so we can verify from the browser.
    Only exposes non-sensitive values (origin list and credential flag)."""
    return {
        "allow_origins": settings.CORS_ORIGINS,
        "allow_credentials": _allow_creds,
        "cors_is_wildcard": settings.cors_is_wildcard,
    }
