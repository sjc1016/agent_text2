"""认证请求/响应 schema（Pydantic）。

PRD 依据：API 契约 /auth/login、/auth/reauth（OpenAPI 自动生成）。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    phone: str = Field(..., description="手机号（11 位）")
    service_password: str = Field(..., description="服务密码")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ReauthRequest(BaseModel):
    service_password: str = Field(..., description="办理执行复核用服务密码")


class ReauthResponse(BaseModel):
    """办理执行复核通过后颁发的短期可执行凭证。"""

    execute_token: str
    token_type: str = "bearer"


class CustomerPublic(BaseModel):
    """当前客户公开档案（/auth/me 响应）。

    仅暴露非敏感字段；service_password_hash 等绝不外泄。
    """

    id: int
    phone: str
    name: str | None = None
