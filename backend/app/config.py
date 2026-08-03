"""应用配置（Pydantic Settings + .env）。

PRD 依据：实现决策 › 配置（Pydantic Settings + .env，dev/staging/prod）。
敏感 key 经 .env 注入，不入仓库。本切片含认证相关配置（JWT、bcrypt）。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )

    # 数据库
    database_url: str = "sqlite:///./app.db"

    # JWT（ADR 0004：access 2h / refresh 7d；execute 短期复核凭证）
    jwt_secret: str = "dev-only-insecure-secret"  # 生产经 .env 注入
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120  # 2h
    refresh_token_expire_days: int = 7  # 7d
    # 办理执行复核凭证（CONTEXT › 办理执行复核）：短期，仅用于 Ticket 执行一步
    execute_token_expire_minutes: int = 10

    # 会话超时（分钟，CONTEXT › 会话片段：超时断开，重新交互开启新 Session）
    session_timeout_minutes: int = 30

    # bcrypt（ADR 0004：成本 12）
    bcrypt_cost: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
