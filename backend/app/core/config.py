from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
import os 

load_dotenv()

ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    app_name: str = "Devita AI Reporting"
    environment: str = "local"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://192.168.1.7:3000"

    database_url: str | None = None
    db_host: str | None = None
    db_port: int = 3306
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None

    username: str | None = None
    password: str | None = None

    ai_provider: str = "openrouter"
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4.1-mini"
    openrouter_intent_model: str | None = None
    openrouter_site_url: str | None = None
    openrouter_app_name: str = "Devita AI Reporting"
    ollama_sql_url: str = "http://localhost:11434/api/chat"
    ollama_sql_model: str = "qwen2.5-coder:3b"
    ollama_sql_timeout_seconds: float = 900
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    ai_sql_enabled: bool = True
    llm_sql_cache_enabled: bool = True
    llm_sql_cache_path: str = "data/llm_sql_cache.json"
    llm_sql_cache_ttl_days: int = 2
    llm_validator_enabled: bool = True
    llm_validator_url: str = "http://localhost:11434/api/chat"
    llm_validator_model: str = "smollm"
    llm_validator_max_retries: int = 10
    llm_validator_timeout_seconds: float = 360
    max_rows: int = 500
    query_timeout_seconds: int = 60

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = "rihasoft2@gmail.com"
    smtp_password: str = os.getenv("GMAIL_PASSWORD")
    smtp_from_email: str = "rihasoft2@gmail.com"
    smtp_from_name: str = "Devita AI Reporting"
    smtp_use_tls: bool = True
     
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str | None:
        if self.database_url and "YOUR_" not in self.database_url:
            return self.database_url
        user = self.db_user or self.username
        password = self.db_password or self.password
        if not all([self.db_host, self.db_name, user, password]):
            return None
        return (
            f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
            "?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
