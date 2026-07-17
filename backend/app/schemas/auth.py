import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import UserRole


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., pattern=r"^[\w.-]+@[\w.-]+\.\w+$")
    password: str = Field(..., min_length=8)
    confirm_password: str

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 个字符")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码需包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码需包含至少一个小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含至少一个数字")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "RegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("confirm_password", "两次输入的密码不一致")
        return self


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    nickname: str | None = None
    avatar: str | None = None
    is_active: bool
    role: UserRole
    auth_provider: str = "local"
    tenant_id: str | None = None


class ProfileUpdateRequest(BaseModel):
    nickname: str | None = Field(None, max_length=100)
    email: str | None = Field(None, pattern=r"^[\w.-]+@[\w.-]+\.\w+$")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_policy(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 个字符")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码需包含至少一个大写字母")
        if not re.search(r"[a-z]", v):
            raise ValueError("密码需包含至少一个小写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含至少一个数字")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "PasswordChangeRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


class AuthConfigResponse(BaseModel):
    allow_user_registration: bool
    oidc_auto_redirect: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_id: str | None = None
