from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "Hanoi Satellite WebGIS"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    # Database
    DATABASE_URL: str = "sqlite:///./data/webgis.db"

    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "webgis-hanoi"
    R2_PUBLIC_URL: Optional[str] = None

    # Microsoft Planetary Computer
    MPC_STAC_URL: str = "https://planetarycomputer.microsoft.com/api/stac/v1"
    PC_SDK_SUBSCRIPTION_KEY: Optional[str] = None

    # Geospatial Settings
    HANOI_BBOX: List[float] = [105.25, 20.55, 106.02, 21.45]
    HANOI_BOUNDARY_PATH: str = "./data/boundaries/hanoi.geojson"
    TEMP_DIR: str = "./data/temp"
    MAX_CLOUD_COVER: float = 40.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
