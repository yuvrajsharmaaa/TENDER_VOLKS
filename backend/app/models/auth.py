import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship

from backend.app.db.session import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    """
    Application identity.

    BIDDER:
        Self-service company account.

    OFFICER:
        Procurement officer account provisioned by administration.
    """

    __tablename__ = "users"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    email = Column(
        String(320),
        unique=True,
        nullable=False,
        index=True,
    )

    full_name = Column(
        String(255),
        nullable=False,
    )

    hashed_password = Column(
        String(255),
        nullable=False,
    )

    role = Column(
        String(30),
        nullable=False,
        default="BIDDER",
        index=True,
    )

    bidder_id = Column(
        String(36),
        ForeignKey("bidders.id"),
        nullable=True,
        index=True,
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
    )

    last_login_at = Column(
        DateTime,
        nullable=True,
    )

    bidder = relationship(
        "Bidder",
        foreign_keys=[bidder_id],
        lazy="joined",
    )


class AuthLog(Base):
    """
    Authentication and account activity trail.
    """

    __tablename__ = "auth_logs"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    email = Column(
        String(320),
        nullable=True,
        index=True,
    )

    event_type = Column(
        String(50),
        nullable=False,
        index=True,
    )

    success = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    ip_address = Column(
        String(100),
        nullable=True,
    )

    user_agent = Column(
        String(1000),
        nullable=True,
    )

    details = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=utc_now,
        index=True,
    )


Index(
    "ix_auth_logs_user_created",
    AuthLog.user_id,
    AuthLog.created_at,
)
