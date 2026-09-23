from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://livepulse:livepulse@localhost:5432/livepulse"
    clerk_issuer: str = ""
    clerk_authorized_parties: list[str] = []
    # Operator-managed grants until the identity administration module is implemented.
    livepulse_user_accounts: dict[str, list[Literal["medical", "medical-2"]]] = {}
    cors_origins: list[str] = []

    @field_validator("livepulse_user_accounts", mode="before")
    @classmethod
    def empty_grants(cls, value):
        return {} if value is None else value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
