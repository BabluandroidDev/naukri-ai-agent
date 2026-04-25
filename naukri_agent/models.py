from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


Decision = Literal["apply", "skip", "needs_manual_review"]


class JobPosting(BaseModel):
    """Normalized job data extracted from Naukri pages."""

    title: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    description: str = ""
    url: str = ""

    def compact_text(self, max_chars: int = 12000) -> str:
        parts = [
            f"Title: {self.title}",
            f"Company: {self.company}",
            f"Location: {self.location}",
            f"Experience: {self.experience}",
            f"URL: {self.url}",
            "Description:",
            self.description,
        ]
        text = "\n".join(part for part in parts if part is not None)
        return text[:max_chars]


class MatchResult(BaseModel):
    """AI match result. Invalid or risky AI output is normalized safely."""

    score: int = Field(default=0, ge=0, le=100)
    decision: Decision = "needs_manual_review"
    reason: str = ""
    risks: list[str] = Field(default_factory=list)
    suggested_recruiter_note: str = ""

    @field_validator("decision", mode="before")
    @classmethod
    def normalize_decision(cls, value: object) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"apply", "skip", "needs_manual_review"}:
                return normalized
        return "needs_manual_review"


class ApplicationLogRow(BaseModel):
    timestamp: str
    job_title: str = ""
    company: str = ""
    location: str = ""
    experience: str = ""
    url: str = ""
    score: int = 0
    decision: Decision = "needs_manual_review"
    status: str = ""
    reason: str = ""
