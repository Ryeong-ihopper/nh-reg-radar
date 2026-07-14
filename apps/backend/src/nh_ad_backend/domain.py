"""Domain records for the M2 authentication and advertisement slice."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass
class User:
    user_id: str
    user_name: str
    email: str
    password_hash: str
    department_id: str
    department_name: str
    roles: tuple[str, ...]
    user_status: str = "ACTIVE"
    auth_token_version: int = 1
    failed_login_count: int = 0
    last_failed_login_at: datetime | None = None
    locked_until: datetime | None = None
    last_login_at: datetime | None = None


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    user_name: str
    department_id: str
    department_name: str
    roles: tuple[str, ...]
    token_version: int


@dataclass
class RefreshSession:
    session_id: str
    user_id: str
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    token_version: int
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


@dataclass(frozen=True)
class AdvertisementFile:
    file_id: str
    file_type: str
    original_file_name: str
    storage_key: str
    mime_type: str
    file_size: int
    checksum: str


@dataclass
class Advertisement:
    advertisement_id: str
    advertisement_name: str
    product_group: str
    advertisement_type: str
    channel_type: str | None
    department_id: str
    owner_user_id: str
    review_status: str
    memo: str | None
    created_at: datetime
    files: list[AdvertisementFile] = field(default_factory=list)
    overall_risk_level: str | None = None
    latest_review_id: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    action_type: str
    result: str
    reason_code: str | None
    actor_user_id: str | None
    actor_department_id: str | None
    actor_role: str | None
    target_type: str | None
    target_id: str | None
    trace_id: str
    created_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)
    audit_log_id: str = field(default_factory=lambda: str(uuid4()))
