"""Settings, read from environment variables (or a local .env file).

Secrets are never written in code: DATABASE_URL and JWT_SECRET_KEY must be
provided by the environment. Locally they live in .env (git-ignored, see
.env.example); in production set them as environment variables.
"""

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Required (no defaults on purpose).
    # e.g. postgresql+psycopg2://user:password@host:5432/smart_classroom
    database_url: str
    # Long random value: python -c "import secrets; print(secrets.token_urlsafe(48))"
    jwt_secret_key: str = Field(min_length=32)

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    # Code a person must enter to register as an admin once an admin exists.
    # Empty = only existing admins can add admins (Users -> Add User).
    admin_registration_code: str = ""
    # Browser origins allowed to call the API (the deployed web app), comma
    # separated, e.g. https://smartclass.example.edu
    cors_origins: str = ""
    # Also allow http://localhost:* / 127.0.0.1:* (local web development).
    cors_allow_localhost: bool = True

    # --- WebRTC network relay (TURN) for live classes -----------------------
    # Without a TURN server, audio/video only connects when both sides can
    # reach each other directly (same Wi-Fi, friendly routers). Over mobile
    # data or strict networks it fails. Configure ONE of the options below.
    # a) Your own / any TURN server: comma-separated URLs, e.g.
    #    turn:turn.example.com:3478,turns:turn.example.com:5349?transport=tcp
    turn_urls: str = ""
    turn_username: str = ""
    turn_credential: str = ""
    # b) Metered.ca (free plan available): app domain + API key of a credential,
    #    e.g. METERED_DOMAIN=myapp.metered.live
    metered_domain: str = ""
    metered_api_key: str = ""
    # c) Cloudflare Realtime TURN: TURN key id + its API token.
    cloudflare_turn_key_id: str = ""
    cloudflare_turn_api_token: str = ""
    # STUN servers (free, no relay), comma separated.
    stun_urls: str = "stun:stun.l.google.com:19302,stun:stun1.l.google.com:19302"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


def _load() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        missing = ", ".join(str(err["loc"][0]).upper() for err in e.errors())
        raise SystemExit(
            f"Configuration error ({missing}). Set these environment variables, or copy "
            ".env.example to .env and fill it in. JWT_SECRET_KEY needs at least 32 characters."
        ) from None


settings = _load()