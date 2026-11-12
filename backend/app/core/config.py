from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"
    DATABASE_URL: str = "sqlite:///./wms.db"
    REDIS_URL: str = ""
    JWT_SECRET: str = "dev-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    CORS_ORIGINS: str = "http://localhost:3000"
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE: str = "memory://"
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./storage"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "wms"
    MINIO_SECURE: bool = False
    MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024
    DEAD_STOCK_DAYS: int = 90
    FAST_MOVE_DAYS: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()


def assert_production_safe(cfg: Settings | None = None) -> None:
    cfg = cfg or settings
    if cfg.ENV != "production":
        return
    secret = cfg.JWT_SECRET
    if secret.startswith("dev-only") or len(secret) < 32:
        raise RuntimeError("Set a JWT_SECRET of at least 32 characters before ENV=production")
    if cfg.STORAGE_BACKEND == "minio" and cfg.MINIO_SECRET_KEY == "minioadmin":
        raise RuntimeError("Replace the MinIO credentials before ENV=production")
