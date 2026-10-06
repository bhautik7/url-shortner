"""
URL Model Definition.

Defines the core `urls` table schema for the URL Shortener.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.base import Base, get_utc_now


class URL(Base):
    """
    SQLAlchemy model representing shortened URLs.

    Indexing Strategy:
    1. Primary Key on `id` (Clustered index in PostgreSQL via standard b-tree).
    2. Unique B-Tree Index on `short_code` (critical for O(log N) lookup on cache miss).
    3. Non-unique Index on `expires_at` (optimized for background cleanup queries:
       `SELECT ... WHERE expires_at IS NOT NULL AND expires_at <= NOW()`).
    """

    __tablename__ = "urls"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    
    # short_code is indexed and unique. It stores either the generated Base62 code or custom alias.
    short_code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique short code or alias for redirection",
    )

    # Standard max length for URLs across modern browsers is ~2048 chars
    long_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Destination long URL",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=get_utc_now,
        nullable=False,
        doc="Timestamp when the short URL was created",
    )

    # Optional expiration. Indexed for fast expiration cleanup queries.
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        doc="Optional expiration timestamp. If null, URL never expires.",
    )

    # Store custom alias separately for auditability and validation
    custom_alias: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        unique=True,
        doc="Custom alias provided by user, if any",
    )

    # Optional creator identifier (user_id, api_key, or client IP)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Identifier of user or system that created the URL",
    )

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """
        Evaluates whether the URL has passed its expiration time.
        """
        if self.expires_at is None:
            return False
        now = current_time or get_utc_now()
        # Ensure comparison is timezone-aware
        if self.expires_at.tzinfo is None:
            now_cmp = now.replace(tzinfo=None)
        else:
            now_cmp = now
        return now_cmp >= self.expires_at

    def __repr__(self) -> str:
        return (
            f"<URL id={self.id} short_code='{self.short_code}' "
            f"long_url='{self.long_url[:30]}...' expires_at={self.expires_at}>"
        )
