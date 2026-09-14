"""Session state management for Placement Hub interviews."""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Literal
from pydantic import BaseModel, Field

from .blueprint import BlueprintTopic


class InterviewTurn(BaseModel):
    turn_index: int
    question: str
    user_answer: str = ""
    audio_duration_seconds: float = 0.0
    turn_timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    evaluation: dict[str, Any] = Field(default_factory=dict)


class VoiceMetrics(BaseModel):
    total_words: int = 0
    speaking_pace_wpm: float = 0.0
    filler_words_count: int = 0
    filler_words_found: list[str] = Field(default_factory=list)
    pause_count: int = 0
    repetition_count: int = 0
    average_answer_length: float = 0.0
    clarity_score: float = 70.0
    structure_feedback: str = "Good communication flow."


class CameraCoachingMetrics(BaseModel):
    facing_camera_percentage: float = 85.0
    looking_away_count: int = 2
    excessive_head_movement_count: int = 1
    posture_consistency_percentage: float = 90.0
    coaching_tips: list[str] = Field(default_factory=list)


class InterviewEvaluationReport(BaseModel):
    overall_score: float = 0.0
    percentile_rank: float = 82.5
    star_method_score: float = 78.0
    category_scores: dict[str, float] = Field(default_factory=dict)
    strong_areas: list[str] = Field(default_factory=list)
    needs_improvement: list[str] = Field(default_factory=list)
    missed_concepts: list[str] = Field(default_factory=list)
    actionable_suggestions: list[str] = Field(default_factory=list)
    question_reviews: list[dict[str, Any]] = Field(default_factory=list)
    voice_metrics: VoiceMetrics = Field(default_factory=VoiceMetrics)
    camera_coaching: CameraCoachingMetrics = Field(default_factory=CameraCoachingMetrics)


class InterviewSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    learner_id: str
    target_role: str
    company_pack: str | None = None
    interview_type: str
    level: str
    duration_minutes: int
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    status: Literal["in_progress", "completed", "cancelled"] = "in_progress"
    
    resume_summary: dict[str, Any] = Field(default_factory=dict)
    blueprint_topics: list[BlueprintTopic] = Field(default_factory=list)
    turns: list[InterviewTurn] = Field(default_factory=list)
    
    # Store aggregated raw coaching metrics sent by browser during session
    camera_raw_events: list[dict[str, Any]] = Field(default_factory=list)
    
    report: InterviewEvaluationReport | None = None
    detected_skill_gaps: list[dict[str, Any]] = Field(default_factory=list)


# In-memory session cache with store persistence fallback
_active_sessions: dict[str, InterviewSession] = {}
_session_history_by_learner: dict[str, list[str]] = {}


def create_session(
    learner_id: str,
    target_role: str,
    interview_type: str,
    level: str,
    duration_minutes: int,
    company_pack: str | None = None,
    resume_summary: dict[str, Any] | None = None,
    topics: list[BlueprintTopic] | None = None,
) -> InterviewSession:
    session = InterviewSession(
        learner_id=learner_id,
        target_role=target_role,
        company_pack=company_pack,
        interview_type=interview_type,
        level=level,
        duration_minutes=duration_minutes,
        resume_summary=resume_summary or {},
        blueprint_topics=topics or [],
    )
    _active_sessions[session.session_id] = session
    _session_history_by_learner.setdefault(learner_id, []).append(session.session_id)
    return session


def get_session(session_id: str) -> InterviewSession | None:
    return _active_sessions.get(session_id)


def update_session(session: InterviewSession) -> None:
    _active_sessions[session.session_id] = session


def get_learner_history(learner_id: str) -> list[InterviewSession]:
    session_ids = _session_history_by_learner.get(learner_id, [])
    return [s for sid in session_ids if (s := _active_sessions.get(sid)) and s.status == "completed"]
