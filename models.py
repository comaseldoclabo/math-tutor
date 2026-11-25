"""Modèle de données.

Multi-espaces : chaque tuteur / centre / école = un Workspace. Les programmes scolaires
(Country > Level > Chapter) sont des DONNÉES : ajouter un pays = ajouter des lignes.
"""
import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- programmes
class Country(Base):
    __tablename__ = "countries"
    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    lang: Mapped[str] = mapped_column(String(5), default="fr")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    grading_max: Mapped[int] = mapped_column(Integer, default=20)  # barème (20, 100, ...)
    system_name: Mapped[str] = mapped_column(String(120), default="")


class Level(Base):
    __tablename__ = "levels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_code: Mapped[str] = mapped_column(ForeignKey("countries.code"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    stage: Mapped[str] = mapped_column(String(40), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------- SaaS
class Plan(Base):
    __tablename__ = "plans"
    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(60))
    max_students: Mapped[int] = mapped_column(Integer, default=5)
    ai_daily_quota: Mapped[int] = mapped_column(Integer, default=10)  # questions IA / élève / jour
    prices: Mapped[str] = mapped_column(Text, default="{}")  # JSON {"XOF": 5000, "USD": 9}
    position: Mapped[int] = mapped_column(Integer, default=0)

    def price_map(self) -> dict:
        return json.loads(self.prices or "{}")


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default="tutor")  # tutor | school
    join_code: Mapped[str] = mapped_column(String(20), unique=True)   # pour les élèves
    tutor_code: Mapped[str] = mapped_column(String(20), unique=True)  # pour les tuteurs invités
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"), default="free")
    plan_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    pw_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(10))  # student | parent | tutor | admin
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("levels.id"), nullable=True)
    lang: Mapped[str] = mapped_column(String(5), default="fr")
    phone: Mapped[str] = mapped_column(String(30), default="")
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    link_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)  # élèves
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    @property
    def is_staff(self) -> bool:
        return self.role in ("tutor", "admin")

    @property
    def can_manage(self) -> bool:
        return self.role == "admin" or (self.role == "tutor" and self.is_owner)


class Classroom(Base):
    __tablename__ = "classrooms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    level_id: Mapped[int | None] = mapped_column(ForeignKey("levels.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ClassroomStudent(Base):
    __tablename__ = "classroom_students"
    classroom_id: Mapped[int] = mapped_column(ForeignKey("classrooms.id"), primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


class ParentChild(Base):
    __tablename__ = "parent_children"
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)


# ---------------------------------------------------------------- contenu & RAG
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(200), default="")
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    level_id: Mapped[int | None] = mapped_column(ForeignKey("levels.id"), nullable=True, index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), nullable=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)


class Exercise(Base):
    __tablename__ = "exercises"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    statement: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(String(200))  # ex: "x=4" ou "x=2 ou x=-2" ou "x^2+2x+1"
    hint: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    answer: Mapped[str] = mapped_column(String(200))
    correct: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (Index("ix_attempt_student_time", "student_id", "created_at"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[str] = mapped_column(Text, default="[]")
    verified: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="info")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(200), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


# ---------------------------------------------------------------- CRM & facturation
LEAD_STATUSES = ["new", "contacted", "trial", "enrolled", "lost"]


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str] = mapped_column(String(120), default="")  # téléphone / WhatsApp / email
    child_level: Mapped[str] = mapped_column(String(60), default="")
    source: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(12), default="new")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id"), index=True)
    plan_code: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    provider: Mapped[str] = mapped_column(String(20), default="demo")
    tx_ref: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | paid | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
