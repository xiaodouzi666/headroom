"""SQLModel records. JSON payloads preserve evidence without inventing measurements."""

from datetime import UTC, datetime

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Run(SQLModel, table=True):
    __tablename__ = "runs"
    id: str = Field(primary_key=True)
    status: str = Field(default="created", index=True)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    event_sequence: int = 0
    data_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class Round(SQLModel, table=True):
    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("run_id", "number"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    number: int
    created_at: str = Field(default_factory=utc_now)
    data_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class Event(SQLModel, table=True):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    sequence: int
    kind: str = Field(index=True)
    created_at: str = Field(default_factory=utc_now)
    data_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class LLMCall(SQLModel, table=True):
    __tablename__ = "llm_calls"
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    model: str = Field(default="unknown", index=True)
    role: str = "unknown"
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: str | None = None
    created_at: str = Field(default_factory=utc_now)
    data_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class Research(SQLModel, table=True):
    __tablename__ = "research"
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="runs.id", index=True)
    created_at: str = Field(default_factory=utc_now)
    data_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
