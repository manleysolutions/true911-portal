import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import auth, sites, telemetry, audits, incidents, notifications, e911, actions, devices, lines, recordings, events, providers, heartbeat, hardware_models, admin

logger = logging.getLogger("true911")

app = FastAPI(title="TRUE911 API", version="1.0.0")

# CORS — wildcard origins and allow_credentials=True are mutually exclusive
# per the Fetch spec.  Browsers silently reject the response when both are set.
# When CORS_ORIGINS is ["*"] we must set allow_credentials=False.
_allow_creds = not settings.cors_is_wildcard

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=_allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """Return a proper JSON 500 so CORSMiddleware can still add headers.

    Without this, unhandled exceptions bypass the middleware stack and the
    browser sees a missing Access-Control-Allow-Origin header — which it
    reports as a CORS error, hiding the real 500 in the Render logs.
    """
    logger.error("Unhandled exception on %s %s:\n%s", request.method, request.url.path, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}: {exc}"},
    )


app.include_router(auth.router,          prefix="/api/auth",      tags=["auth"])
app.include_router(sites.router,         prefix="/api/sites",     tags=["sites"])
app.include_router(telemetry.router,     prefix="/api/telemetry", tags=["telemetry"])
app.include_router(audits.router,        prefix="/api/audits",    tags=["audits"])
app.include_router(incidents.router,     prefix="/api/incidents", tags=["incidents"])
app.include_router(notifications.router, prefix="/api")
app.include_router(e911.router,          prefix="/api")
app.include_router(actions.router,       prefix="/api")
app.include_router(devices.router,      prefix="/api/devices",    tags=["devices"])
app.include_router(lines.router,        prefix="/api/lines",      tags=["lines"])
app.include_router(recordings.router,   prefix="/api/recordings", tags=["recordings"])
app.include_router(events.router,       prefix="/api/events",     tags=["events"])
app.include_router(providers.router,   prefix="/api/providers",  tags=["providers"])
app.include_router(heartbeat.router,  prefix="/api/heartbeat",  tags=["heartbeat"])
app.include_router(hardware_models.router, prefix="/api/hardware-models", tags=["hardware-models"])
app.include_router(admin.router,     prefix="/api/admin",      tags=["admin"])


@app.get("/api/config/features")
async def feature_flags():
    """Return feature flags for the frontend."""
    return {
        "samantha": settings.FEATURE_SAMANTHA.lower() == "true",
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "app_mode": settings.APP_MODE}


@app.get("/api/debug/cors")
async def debug_cors():
    """Return resolved CORS config so we can verify from the browser.
    Only exposes non-sensitive values (origin list and credential flag)."""
    return {
        "allow_origins": settings.cors_origin_list,
        "allow_credentials": _allow_creds,
        "cors_is_wildcard": settings.cors_is_wildcard,
    }
