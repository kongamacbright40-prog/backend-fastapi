from pydantic_settings import BaseSettings #a class built specifially for reading configuration

class Settings(BaseSettings):#defining our own class 
    database_url: str = "sqlite:///./dev.db"
    jwt_secret_key: str = "dev-secret-change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int= 7
#jwt: json web token settings means is what permits us to enter the app several time without re-authentication
    class Config:
        env_file = ".env"

settings = Settings()
