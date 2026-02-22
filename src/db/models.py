import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums matching the OSINT guide taxonomy ──────────────────────────────────


class EventType(str, enum.Enum):
    REGULATION = "Regulation"
    FX_VOLATILITY = "FX Volatility"
    PORT_CONGESTION = "Port Congestion"
    ENFORCEMENT = "Enforcement"
    TRADE_REMEDY = "Trade Remedy"
    SHIPPING_SCHEDULE = "Shipping Schedule"
    CUSTOMS = "Customs"
    INPUT_PRICE = "Input Price"
    PORT_OPERATIONS = "Port Operations"
    OTHER = "Other"


class Jurisdiction(str, enum.Enum):
    UK = "UK"
    INDIA = "India"
    VIETNAM = "Vietnam"
    EGYPT = "Egypt"
    BILATERAL = "Bilateral"


class EventStatus(str, enum.Enum):
    DRAFT = "Draft"
    ANNOUNCED = "Announced"
    ENFORCED = "Enforced"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class IndexType(str, enum.Enum):
    RPI = "RPI"
    LSI = "LSI"
    CPI = "CPI"


class SourceLayer(str, enum.Enum):
    PRIMARY = "Primary"
    LOGISTICS = "Logistics"
    MARKET = "Market"
    INDUSTRY = "Industry"


class HealthStatus(str, enum.Enum):
    STABLE = "STABLE"
    WATCH = "WATCH"
    ACTIVE = "ACTIVE"


class LaneStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"


class CheckFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


# ── Models ───────────────────────────────────────────────────────────────────


class TradeLane(Base):
    __tablename__ = "trade_lanes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "UK-India"
    sector: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Textiles"
    status: Mapped[LaneStatus] = mapped_column(
        Enum(LaneStatus), default=LaneStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sources: Mapped[list["OsintSource"]] = relationship(back_populates="trade_lane")
    events: Mapped[list["Event"]] = relationship(back_populates="trade_lane")
    index_snapshots: Mapped[list["IndexSnapshot"]] = relationship(
        back_populates="trade_lane"
    )
    lane_health_records: Mapped[list["LaneHealth"]] = relationship(
        back_populates="trade_lane"
    )


class OsintSource(Base):
    __tablename__ = "osint_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_lane_id: Mapped[int] = mapped_column(ForeignKey("trade_lanes.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_layer: Mapped[SourceLayer] = mapped_column(Enum(SourceLayer), nullable=False)
    primary_index: Mapped[IndexType] = mapped_column(Enum(IndexType), nullable=False)
    check_frequency: Mapped[CheckFrequency] = mapped_column(
        Enum(CheckFrequency), nullable=False
    )
    source_weight: Mapped[float] = mapped_column(Float, nullable=False)

    trade_lane: Mapped["TradeLane"] = relationship(back_populates="sources")
    events: Mapped[list["Event"]] = relationship(back_populates="source")


class Event(Base):
    """Core 18-column OSINT event log — matches the Excel framework exactly."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_lane_id: Mapped[int] = mapped_column(ForeignKey("trade_lanes.id"))
    source_id: Mapped[int] = mapped_column(ForeignKey("osint_sources.id"))

    # Columns 1-4: Source identification
    date_observed: Mapped[date] = mapped_column(Date, nullable=False)
    source_layer: Mapped[SourceLayer] = mapped_column(Enum(SourceLayer), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Columns 5-9: Event classification
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(Enum(Jurisdiction), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    affected_object: Mapped[str] = mapped_column(String(300), nullable=False)
    event_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Columns 10-12: Assessment
    event_status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), nullable=False)
    confidence_level: Mapped[ConfidenceLevel] = mapped_column(
        Enum(ConfidenceLevel), nullable=False
    )
    historical_precedent: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Columns 13-16: Impact and scoring
    impact_pathway: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # "Cost", "Time", "Compliance;Time", etc.
    quant_metric_triggered: Mapped[str] = mapped_column(String(300), nullable=False)
    index_impact: Mapped[IndexType] = mapped_column(Enum(IndexType), nullable=False)
    index_delta: Mapped[int] = mapped_column(Integer, nullable=False)  # +1, 0, -1

    # Columns 17-18: Review
    analyst_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trade_lane: Mapped["TradeLane"] = relationship(back_populates="events")
    source: Mapped["OsintSource"] = relationship(back_populates="events")
    weighted_score: Mapped["WeightedScore | None"] = relationship(
        back_populates="event", uselist=False
    )


class WeightedScore(Base):
    """Computed weighted score per event using Danha's weight matrix."""

    __tablename__ = "weighted_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True)

    weighted_score: Mapped[float] = mapped_column(Float, nullable=False)
    source_weight: Mapped[float] = mapped_column(Float, nullable=False)
    status_weight: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_weight: Mapped[float] = mapped_column(Float, nullable=False)
    precedent_weight: Mapped[float] = mapped_column(Float, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    event: Mapped["Event"] = relationship(back_populates="weighted_score")


class IndexSnapshot(Base):
    """Daily/weekly index values with EWMA baseline and CUSUM state."""

    __tablename__ = "index_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_lane_id: Mapped[int] = mapped_column(ForeignKey("trade_lanes.id"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    index_type: Mapped[IndexType] = mapped_column(Enum(IndexType), nullable=False)

    raw_total: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_total: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ewma_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    ewma_sigma: Mapped[float | None] = mapped_column(Float, nullable=True)
    cusum_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    cusum_lower: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trade_lane: Mapped["TradeLane"] = relationship(back_populates="index_snapshots")


class LaneHealth(Base):
    """Weekly lane health status roll-up."""

    __tablename__ = "lane_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_lane_id: Mapped[int] = mapped_column(ForeignKey("trade_lanes.id"))
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)

    rpi_total: Mapped[float] = mapped_column(Float, nullable=False)
    lsi_total: Mapped[float] = mapped_column(Float, nullable=False)
    cpi_total: Mapped[float] = mapped_column(Float, nullable=False)
    combined_total: Mapped[float] = mapped_column(Float, nullable=False)
    health_status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trade_lane: Mapped["TradeLane"] = relationship(
        back_populates="lane_health_records"
    )
