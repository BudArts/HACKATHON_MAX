from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: Any = None


class MaxAuthRequest(BaseModel):
    init_data: str = Field(min_length=16, max_length=4096)

    @field_validator("init_data")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Пустые стартовые данные")
        return stripped


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class ConsentItem(ORMModel):
    purpose: str
    policy_code: str
    policy_version: str
    granted_at: datetime
    source: str


class ConsentDecision(BaseModel):
    accept: bool = True


class ConsentState(BaseModel):
    purpose: str
    granted: bool
    policy_code: str
    policy_version: str
    granted_at: datetime | None = None
    revoked_at: datetime | None = None


class PolicyView(BaseModel):
    code: str
    version: str
    title: str
    body: str


class UserView(ORMModel):
    id: UUID
    role: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    locale: str
    grade: int | None = None
    is_active: bool
    has_phone: bool = False
    has_email: bool = False
    created_at: datetime

    @classmethod
    def from_user(cls, user: Any) -> UserView:
        return cls(
            id=user.id,
            role=user.role.value,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username,
            locale=user.locale,
            grade=user.grade,
            is_active=user.is_active,
            has_phone=bool(user.phone_index),
            has_email=bool(user.email_index),
            created_at=user.created_at,
        )


class PhoneShareRequest(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    auth_date: str = Field(min_length=8, max_length=20)
    hash: str = Field(min_length=32, max_length=128)


class ProfileUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip().lower()
        if not candidate:
            return None
        if candidate.count("@") != 1 or "." not in candidate.split("@")[-1]:
            raise ValueError("Некорректный адрес электронной почты")
        return candidate


class AuthResponse(BaseModel):
    user: UserView
    tokens: TokenPair | None
    consents: list[ConsentState]
    onboarding_required: bool


class TaskThreadMessage(BaseModel):
    author: str
    content: str
    created_at: datetime


class DraftRequest(BaseModel):
    appeal_id: UUID
    note: str = Field(default="", max_length=1000)


class DraftResponse(BaseModel):
    text: str
    model: str
    refused: bool


class NotificationView(ORMModel):
    id: UUID
    kind: str
    title: str
    body: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read_at: datetime | None = None


class PersonalDataReport(BaseModel):
    profile: UserView
    consents: list[ConsentState]
    tasks_total: int
    notifications_total: int
    audit_entries: list[dict[str, Any]]


class DevUserView(BaseModel):
    max_user_id: int
    role: str
    first_name: str | None = None
    last_name: str | None = None


class DevInitDataResponse(BaseModel):
    init_data: str
    max_user_id: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["up", "down"]
    max_api: Literal["configured", "missing"]
    gigachat: Literal["ready", "disabled"]
    time: datetime
