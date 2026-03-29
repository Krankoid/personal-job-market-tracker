from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    site = Column(String, nullable=False)          # "jobteaser" | "studerendeonline"
    title = Column(Text, nullable=False)
    company = Column(Text)
    url = Column(Text, unique=True, nullable=False)
    description = Column(Text)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

    skills = relationship("JobSkill", back_populates="job", cascade="all, delete-orphan")


class JobSkill(Base):
    __tablename__ = "job_skills"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    skill_name = Column(String, nullable=False)
    category = Column(String, nullable=False)

    job = relationship("Job", back_populates="skills")

    __table_args__ = (
        UniqueConstraint("job_id", "skill_name", name="uq_job_skill"),
    )
