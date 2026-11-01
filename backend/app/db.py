"""Database models and session handling (works on PostgreSQL and SQLite)."""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, create_engine, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Posting(Base):
    __tablename__ = "postings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external"),
        Index("ix_postings_posted_at", "posted_at"),
        Index("ix_postings_last_seen", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(2))
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_is_predicted: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1000))
    keyword: Mapped[str | None] = mapped_column(String(100))
    posted_at: Mapped[datetime] = mapped_column(DateTime)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    skills: Mapped[list["SkillCount"]] = relationship(
        back_populates="posting", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "state": self.state,
            "is_remote": self.is_remote,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_is_predicted": self.salary_is_predicted,
            "url": self.url,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "skills": sorted(s.skill for s in self.skills),
        }


class SkillCount(Base):
    """One row per (posting, skill) pair, as in the project scope."""
    __tablename__ = "skill_counts"
    __table_args__ = (UniqueConstraint("posting_id", "skill", name="uq_posting_skill"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("postings.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(50), index=True)

    posting: Mapped[Posting] = relationship(back_populates="skills")


class ProviderHealth(Base):
    """Remembers how each provider is doing, so a broken one is rested, not retried forever."""
    __tablename__ = "provider_health"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_fetched: Mapped[int] = mapped_column(Integer, default=0)
    last_new: Mapped[int] = mapped_column(Integer, default=0)
    requests_day: Mapped[date | None] = mapped_column(Date)
    requests_today: Mapped[int] = mapped_column(Integer, default=0)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {
            "name": self.name,
            "consecutive_failures": self.consecutive_failures,
            "cooldown_until": iso(self.cooldown_until),
            "last_run_at": iso(self.last_run_at),
            "last_success_at": iso(self.last_success_at),
            "last_error": self.last_error,
            "last_fetched": self.last_fetched,
            "last_new": self.last_new,
            "requests_today": self.requests_today if self.requests_day == date.today() else 0,
            "total_runs": self.total_runs,
            "total_failures": self.total_failures,
        }


class RefreshRun(Base):
    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|ok|partial|failed
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    pruned: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[str | None] = mapped_column(Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "fetched": self.fetched,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "pruned": self.pruned,
        }


class Database:
    def __init__(self, url: str):
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(pool_size=3, max_overflow=2, pool_recycle=300)
        self.engine = create_engine(url, **kwargs)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def wait_until_ready(self, attempts: int = 5, delay: float = 2.0) -> None:
        """Neon's free tier sleeps when idle; the first connection can fail. Retry it."""
        for i in range(1, attempts + 1):
            try:
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return
            except Exception as exc:  # pragma: no cover - depends on network
                if i == attempts:
                    raise
                log.warning("Database not ready (attempt %s/%s): %s", i, attempts, exc)
                time.sleep(delay * i)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self):
        s = self.Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
