"""认证相关的 Pydantic 请求/响应模型。

登录标识三合一：邮箱 / 手机号 / 账号名（username）任一 + 密码。
- LoginRequest.account：统一登录字段，按内容自动识别（@ → 邮箱、
  1 开头 11 位数字 → 手机号、其余 → 账号名）；email 字段保留兼容旧客户端。
- 注册提供邮箱或手机号其一，账号名缺省时自动生成并与该邮箱/手机号绑定。
"""
import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

# 中国大陆手机号
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
# 账号名：3~32 位字母数字下划线短横线
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")


class RegisterRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=100)
    # 账号名：缺省时由服务端自动生成
    username: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _check_identifier(self) -> "RegisterRequest":
        if self.phone and not PHONE_RE.fullmatch(self.phone):
            raise ValueError("手机号格式不正确")
        if self.username and not USERNAME_RE.fullmatch(self.username):
            raise ValueError("账号名需为 3~32 位字母、数字、下划线或短横线")
        if not self.email and not self.phone:
            raise ValueError("邮箱与手机号至少提供一个")
        return self


class LoginRequest(BaseModel):
    # 邮箱 / 手机号 / 账号名 统一登录字段
    account: str | None = Field(default=None, max_length=255)
    # 兼容旧客户端：仅传 email + password 也可登录
    email: EmailStr | None = None
    password: str

    @model_validator(mode="after")
    def _check_account(self) -> "LoginRequest":
        if not (self.account or self.email):
            raise ValueError("请提供登录账号（邮箱/手机号/账号名）")
        return self

    @property
    def identifier(self) -> str:
        """统一的登录标识（小写）。"""
        return (self.account or self.email or "").strip().lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    phone: str | None = None
    username: str | None = None
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class RegisterResponse(BaseModel):
    id: str
    email: EmailStr
    phone: str | None = None
    username: str | None = None
    full_name: str | None
    role: str


class UserUpdateMe(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class RoleUpdate(BaseModel):
    role: str  # admin / analyst / operator
