from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Strava
    STRAVA_CLIENT_ID: str = ""
    STRAVA_CLIENT_SECRET: str = ""
    STRAVA_ACCESS_TOKEN: str = ""
    STRAVA_REFRESH_TOKEN: str = ""

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/strava_chat"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o"

    class Config:
        env_file = ".env"


settings = Settings()
