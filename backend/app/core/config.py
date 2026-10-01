from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    PROJECT_NAME: str = "SafeZone"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Server binding
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_BASE_URL: str = "http://localhost:8000"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://10.0.2.2:8000",
    ]

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/safezone_db"
    ASYNC_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/safezone_db"

    # Security & JWT
    JWT_SECRET: str = "safezone-insecure-dev-secret-key-change-in-production-32char"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Mobile API Configuration
    MOBILE_API_BASE_URL: str = "http://10.0.2.2:8000"

    # Routing & Optimization
    ROUTING_SERVICE_URL: str = "http://router.project-osrm.org"
    DEFAULT_COVERAGE_RADIUS_KM: float = 3.0
    RISK_RECENCY_LAMBDA: float = 0.05
    DEFAULT_PATROL_COUNT: int = 10

    # Deep Learning Classifier
    CLASSIFICATION_MODEL_PATH: str = "backend/app/ml/saved_models/bilstm_crime_classifier.keras"
    CLASSIFICATION_TOKENIZER_PATH: str = "backend/app/ml/saved_models/tokenizer.json"
    CLASSIFICATION_CONFIDENCE_THRESHOLD: float = 0.75

    # Firebase Notifications Abstraction
    FIREBASE_CREDENTIALS_PATH: str = ""
    FIREBASE_PROJECT_ID: str = ""

    # Twilio SMS Integration
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_TRIAL_MODE: bool = False
    TWILIO_TRIAL_TEMPLATE: str = "sms_account_alerts"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
