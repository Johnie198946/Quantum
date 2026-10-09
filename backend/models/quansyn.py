"""Private delivery records; execution and bytes retain their existing owners."""
from datetime import datetime
from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base


class QuanSynTransfer(Base):
    __tablename__ = "quansyn_transfers"
    __table_args__ = (UniqueConstraint("tenant_key", "user_id", "request_id", name="uq_quansyn_request"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    request_id: Mapped[str] = mapped_column(String(100))
    digest: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(16))
    target: Mapped[str] = mapped_column(String(16))
    reply_to: Mapped[str | None] = mapped_column(String(40), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    files: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    claim_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class QuanSynDevice(Base):
    __tablename__ = "quansyn_devices"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    sender_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(default=False)
