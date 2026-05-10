from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_PROVIDER: Literal["ollama", "openrouter"] = "ollama"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4:e4b"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "anthropic/claude-haiku-4-5"
    OPENROUTER_APP_URL: str = "http://localhost:3000"
    OPENROUTER_APP_NAME: str = "geo-agent"

    WFS_BASE_URL: str = (
        "https://api.accept.montreal.ca/api/it-platforms/geomatic/wfs-maps/montreal/ows"
    )
    WFS_HTTP_TIMEOUT_SECONDS: int = 30

    DATA_DIR: Path = Path("./data")

    MAX_FEATURES_PER_QUERY: int = 5000
    MAX_FILTER_GEOMETRY_VERTICES: int = 1000

    @property
    def results_dir(self) -> Path:
        return self.DATA_DIR / "results"

    @property
    def sessions_dir(self) -> Path:
        return self.DATA_DIR / "sessions"


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
