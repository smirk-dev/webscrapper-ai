from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost:5432/advuman"
    anthropic_api_key: str = ""

    # EWMA decay parameters (lambda = 1 - 2^(-1/H), H = half-life in days)
    ewma_lambda_rpi: float = 0.048  # 14-day half-life
    ewma_lambda_lsi: float = 0.048
    ewma_lambda_cpi: float = 0.048

    # CUSUM parameters
    cusum_k: float = 0.5   # reference value (detects 1-sigma shifts)
    cusum_h: float = 4.5   # control limit (alarm threshold)

    # Lane Health thresholds
    lane_health_watch: int = 4   # combined >= 4 → WATCH
    lane_health_active: int = 8  # combined >= 8 → ACTIVE

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value

        normalized = value.strip().strip('"').strip("'")
        if normalized.startswith("postgres://"):
            normalized = "postgresql+asyncpg://" + normalized[len("postgres://") :]
        elif normalized.startswith("postgresql://") and not normalized.startswith("postgresql+asyncpg://"):
            normalized = "postgresql+asyncpg://" + normalized[len("postgresql://") :]

        return normalized

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
