from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.db.database import init_db
from app.services.strava import get_auth_url, exchange_token
from app.api.chat import router as chat_router

app = FastAPI(title="Strava Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")


@app.on_event("startup")
def startup():
    try:
        init_db()
    except Exception as e:
        print(f"Database init failed (ensure PostgreSQL is running): {e}")


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
