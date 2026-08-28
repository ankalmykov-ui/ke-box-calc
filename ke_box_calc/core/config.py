from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_log_level: str = "INFO"
    database_url: str | None = None
    database_required: bool = False
    allowed_origins: tuple[str, ...] = ("http://localhost:8000",)

    @field_validator("database_url", mode="before")
    @classmethod
    def blank_database_url_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()

