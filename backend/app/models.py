from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Float,
    String,
    Integer,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

# ``origin`` values for entities that come from Keitaro vs. were added locally.
ORIGIN_KEITARO = "keitaro"
ORIGIN_LOCAL = "local"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CampaignCreationLog(Base):
    __tablename__ = "campaign_creation_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_name: Mapped[str] = mapped_column(String(255))
    geo: Mapped[str] = mapped_column(String(255))
    offer_id: Mapped[int] = mapped_column(Integer)
    keitaro_campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    google_stream_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offer_stream_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="started")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(64), nullable=True)
    type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    domain_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    traffic_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_creation_log_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("campaign_creation_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # Editor metadata: last successful loads/pushes and optimistic concurrency.
    last_loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Stream.id",
    )
    offers: Mapped[list["Offer"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Offer.id",
    )


class Stream(Base):
    __tablename__ = "streams"
    __table_args__ = (
        UniqueConstraint("campaign_id", "keitaro_id", name="uq_streams_campaign_keitaro_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # Extra snapshot fields from Keitaro.
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    keitaro_updated_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Local working state.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ORIGIN_KEITARO, server_default=ORIGIN_KEITARO
    )

    # Baseline: last confirmed Keitaro state.
    base_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="streams")
    offers: Mapped[list["Offer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Offer.id",
    )


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        UniqueConstraint("stream_id", "keitaro_id", name="uq_offers_stream_keitaro_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, nullable=False)
    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stream_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("streams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    # ``OfferStream.id`` from Keitaro. Diagnostic only: matching is by ``offer_id``.
    keitaro_offer_stream_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Local working state.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    pinned_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ORIGIN_KEITARO, server_default=ORIGIN_KEITARO
    )

    # Baseline: last confirmed Keitaro state.
    base_share: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="offers")
    stream: Mapped["Stream"] = relationship(back_populates="offers")

    @property
    def keitaro_stream_id(self) -> int | None:
        return self.stream.keitaro_id if self.stream is not None else None
