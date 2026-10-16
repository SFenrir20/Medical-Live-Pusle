from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://livepulse:livepulse@localhost:5432/livepulse"
    clerk_issuer: str = ""
    clerk_authorized_parties: list[str] = []
    # Roles are assigned in Clerk (user Public metadata: {"livepulse": {"role": "..."}}).
    # The session token carries them in this claim (Sessions > Customize session token:
    # {"metadata": "{{user.public_metadata}}"}).
    clerk_roles_claim: str = "metadata"
    # Optional. Only used when the session token does NOT carry the claim yet: the role is
    # then read from the Clerk Backend API. Never put this key in a frontend variable.
    clerk_secret_key: str = ""
    admin_user_ids: list[str] = []
    # Service tokens (Authorization: Bearer). Empty = that credential is disabled.
    social_live_token: str = ""          # Medical Social Live: write events
    medical360_token: str = ""           # Medical 360: read statistics
    medical360_export_token: str = ""    # Medical 360: also export detailed comments
    comments_retention_days: int = 30
    # A contact marked as contacted who sends the number AGAIN in the same live is only
    # suspicious after this many minutes (before that it is just the message in flight).
    alert_same_live_minutes: int = 10
    # Reminders for sales agents about chats still pending.
    reminder_first_minutes: int = 10
    reminder_second_minutes: int = 20
    # Private messages are not captured by any integration. Flip only when one exists.
    dm_capture_connected: bool = False
    cors_origins: list[str] = []
    # Captura TikTok: account_id interno -> usuario TikTok (sin @).
    tiktok_accounts: dict[str, str] = {"medical": "medical.cirugias", "medical-2": "medical.cirugias2"}
    monitor_reconnect_base_s: float = 2.0
    monitor_reconnect_max_s: float = 60.0
    # Gracia antes de confirmar fin de LIVE tras LiveEndEvent (s).
    monitor_end_grace_s: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
