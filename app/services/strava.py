import httpx
from app.core.config import settings

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
REDIRECT_URI = "http://localhost:8000/auth/callback"


def get_auth_url() -> str:
    """Generate Strava authorization URL for the user to open in a browser."""
    return (
        f"{STRAVA_AUTH_URL}"
        f"?client_id={settings.STRAVA_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=read,activity:read_all"
    )


async def exchange_token(code: str) -> dict:
    """Exchange authorization code for access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.STRAVA_CLIENT_ID,
                "client_secret": settings.STRAVA_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            },
        )
        return response.json()


async def refresh_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.STRAVA_CLIENT_ID,
                "client_secret": settings.STRAVA_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        return response.json()


async def fetch_activities(
    access_token: str, page: int = 1, per_page: int = 50, after: int | None = None
) -> list:
    """Fetch activity list. `after` is a Unix timestamp to filter newer activities only."""
    params: dict = {"page": page, "per_page": per_page}
    if after is not None:
        params["after"] = after
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        return response.json()


async def fetch_all_activities(access_token: str, after: int | None = None) -> list:
    """Fetch all activities with pagination. Pass `after` (Unix timestamp) for incremental sync."""
    all_activities = []
    page = 1
    while True:
        activities = await fetch_activities(
            access_token, page=page, per_page=100, after=after
        )
        if not activities:
            break
        all_activities.extend(activities)
        page += 1
        print(f"  Fetched {len(all_activities)} activities...")
    return all_activities
