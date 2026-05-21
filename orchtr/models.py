import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    researcher_comment: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    published_pdf_path: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    published_image_paths: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    images: Mapped[list["ProjectImage"]] = relationship(
        "ProjectImage", back_populates="project", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectImage(Base):
    __tablename__ = "project_images"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    lid: Mapped[str] = mapped_column(String, nullable=False)
    thumb_url: Mapped[str] = mapped_column(String, nullable=False)
    sol: Mapped[str] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="images")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_results: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="messages")


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (
        Index("ix_analysis_artifacts_product_status_created", "product_lid", "status", "created_at"),
        Index("ix_analysis_artifacts_project_product", "project_id", "product_lid"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_lid: Mapped[str] = mapped_column(String, nullable=False, index=True)
    photo_id: Mapped[str] = mapped_column(String, nullable=False)
    sol: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    result_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    evictable_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
