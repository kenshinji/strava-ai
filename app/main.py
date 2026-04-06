from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.config import settings
from app.db.database import init_db
from app.services.strava import get_auth_url, exchange_token
from app.services.sync import run_sync, run_sync_job
from app.api.chat import router as chat_router

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        init_db()
    except Exception as e:
        print(f"Database init failed (ensure PostgreSQL is running): {e}")

    scheduler.add_job(
        run_sync_job,
        trigger="interval",
        hours=settings.SYNC_INTERVAL_HOURS,
        id="strava_sync",
        replace_existing=True,
    )
    scheduler.start()
    print(f"Strava sync scheduler started (every {settings.SYNC_INTERVAL_HOURS}h)")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)


app = FastAPI(title="Strava Chat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth")
def auth_start():
    """Return Strava authorization URL."""
    if not settings.STRAVA_CLIENT_ID or not settings.STRAVA_CLIENT_SECRET:
        return {
            "error": "Please configure STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env first",
            "auth_url": None,
        }
    return {"auth_url": get_auth_url()}


@app.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request):
    """OAuth callback: receive code, exchange for token, return result for user to add to .env."""
    code = request.query_params.get("code")
    if not code:
        return """
        <html><body>
        <h2>Missing code parameter</h2>
        <p>Please visit <a href="/auth">/auth</a> to get the authorization link, then complete Strava authorization in your browser.</p>
        </body></html>
        """

    try:
        result = await exchange_token(code)
        if "errors" in result:
            return f"""
            <html><body>
            <h2>Token exchange failed</h2>
            <pre>{result}</pre>
            </body></html>
            """

        access_token = result.get("access_token", "")
        refresh_token = result.get("refresh_token", "")

        return f"""
        <html><body style="font-family: sans-serif; max-width: 600px; margin: 2em auto;">
        <h2>Strava authorization successful!</h2>
        <p>Add the following to your <code>.env</code> file:</p>
        <pre style="background: #f5f5f5; padding: 1em; overflow-x: auto;">
STRAVA_ACCESS_TOKEN={access_token}
STRAVA_REFRESH_TOKEN={refresh_token}
        </pre>
        <p><strong>Note:</strong> access_token expires in ~6 hours; use refresh_token to obtain a new one.</p>
        </body></html>
        """
    except Exception as e:
        return f"""
        <html><body>
        <h2>Token exchange error</h2>
        <pre>{e}</pre>
        </body></html>
        """


@app.post("/api/sync")
async def trigger_sync(full: bool = False) -> JSONResponse:
    """
    Manually trigger a Strava data sync.
    - `full=false` (default): incremental, only fetches activities newer than the latest in DB.
    - `full=true`: re-fetches all activities from Strava.
    """
    result = await run_sync(full=full)
    return JSONResponse(content=result)
