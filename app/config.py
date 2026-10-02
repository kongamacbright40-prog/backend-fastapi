import logging

from pydantic_settings import BaseSettings #a class built specifially for reading configuration

DEFAULT_JWT_SECRET = "dev-secret-change-this-in-production"


class Settings(BaseSettings):#defining our own class 
    database_url: str = "sqlite:///./dev.db"
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int= 7
    # Code a person must enter to register as an admin once an admin exists.
    # Empty = only existing admins can add admins (Users → Add User).
    admin_registration_code: str = ""
#jwt: json web token settings means is what permits us to enter the app several time without re-authentication
    class Config:
        env_file = ".env"

settings = Settings()

if settings.jwt_secret_key == DEFAULT_JWT_SECRET:
    logging.getLogger("smart_class.config").warning(
        "JWT_SECRET_KEY is not set: using the public development secret. "
        "Anyone can forge login tokens; set JWT_SECRET_KEY in .env before deploying."
    )
