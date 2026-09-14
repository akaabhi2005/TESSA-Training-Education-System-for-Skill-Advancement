"""FastAPI API Router for Placement Hub mock interviews and job matching."""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import store
from ..interview.blueprint import get_blueprint, InterviewSetupRequest
from ..interview.session import (
    create_session,
    get_session,
    update_session,
    get_learner_history,
    InterviewTurn,
    InterviewSession,
)
from ..interview.resume_parser import extract_text_from_pdf, validate_and_parse_resume, parse_resume_to_structured_profile
from ..interview.interviewer import generate_initial_question, generate_next_adaptive_question
from ..interview.evaluator import evaluate_interview_session
from ..interview.skill_gap import extract_skill_gaps, apply_gaps_to_tessa_profile
from ..interview.job_matcher import fetch_live_jobs, calculate_job_match

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/interview", tags=["placement_hub"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class StartInterviewRequest(BaseModel):
    learner_id: str
    target_role: str = "Java Backend Developer"
    company_pack: str | None = None
    interview_type: str = "Technical"
    level: str = "Fresher"
    duration_minutes: int = 30
    resume_summary: dict[str, Any] | None = None


class RespondTurnRequest(BaseModel):
    session_id: str
    user_answer: str
    audio_duration_seconds: float = 0.0


class CameraEventRequest(BaseModel):
    session_id: str
    facing_camera: bool = True
    good_posture: bool = True
    excessive_head_movement: bool = False


class ApplyGapsRequest(BaseModel):
    learner_id: str
    session_id: str


class JobMatchRequest(BaseModel):
    learner_id: str
    target_role: str = "Java Backend Developer"
    location: str = "India"


@router.post("/resume")
async def upload_and_parse_resume(
    file: UploadFile | None = File(default=None),
    resume_text: str | None = Form(default=None),
) -> dict[str, Any]:
    """Validate and parse resume PDF or text into structured profile data."""
    raw_text = ""
    if file and file.filename:
        content = await file.read()
        if file.filename.lower().endswith(".pdf"):
            raw_text = extract_text_from_pdf(content)
        else:
            raw_text = content.decode("utf-8", errors="ignore")
    elif resume_text:
        raw_text = resume_text

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in file upload.")

    valid, reason, structured = validate_and_parse_resume(raw_text)
    if not valid:
        raise HTTPException(status_code=400, detail=reason or "Uploaded file is not a valid Resume/CV. Please upload a genuine resume.")

    return {
        "parsed": True,
        "message": "Resume verified and parsed successfully.",
        "profile": structured,
        "raw_text_snippet": raw_text[:300],
    }


@router.post("/start")
def start_interview(req: StartInterviewRequest) -> dict[str, Any]:
    """Initialize a mock interview session and return opening question."""
    profile = store.get_profile(req.learner_id)
    topics = get_blueprint(req.target_role, req.interview_type, company_pack=req.company_pack)
    
    session = create_session(
        learner_id=req.learner_id,
        target_role=req.target_role,
        company_pack=req.company_pack,
        interview_type=req.interview_type,
        level=req.level,
        duration_minutes=req.duration_minutes,
        resume_summary=req.resume_summary or {},
        topics=topics,
    )

    first_question = generate_initial_question(
        target_role=req.target_role,
        interview_type=req.interview_type,
        level=req.level,
        topics=topics,
        resume_summary=req.resume_summary,
    )

    turn = InterviewTurn(turn_index=1, question=first_question)
    session.turns.append(turn)
    update_session(session)

    return {
        "session_id": session.session_id,
        "target_role": session.target_role,
        "company_pack": session.company_pack,
        "interview_type": session.interview_type,
        "level": session.level,
        "duration_minutes": session.duration_minutes,
        "question": first_question,
        "turn_index": 1,
        "blueprint_topics": [t.name for t in topics],
    }


@router.post("/respond")
def respond_turn(req: RespondTurnRequest) -> dict[str, Any]:
    """Record user answer turn and return adaptive follow-up or completion signal."""
    session = get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Interview session not found.")
    
    if session.status != "in_progress":
        raise HTTPException(400, "Interview session is already finalized.")

    # Record current turn answer
    if session.turns:
        session.turns[-1].user_answer = req.user_answer.strip()
        session.turns[-1].audio_duration_seconds = max(req.audio_duration_seconds, 0.0)

    # Max turns based on duration (15 min -> 4 turns, 30 min -> 7 turns, 45 min -> 10 turns)
    max_turns = max(session.duration_minutes // 4, 4)
    
    if len(session.turns) >= max_turns:
        return {
            "completed": True,
            "message": "Maximum interview duration reached. Please conclude the session to view your report.",
            "next_question": None,
            "turn_index": len(session.turns),
        }

    next_q = generate_next_adaptive_question(
        target_role=session.target_role,
        interview_type=session.interview_type,
        level=session.level,
        topics=session.blueprint_topics,
        turns=session.turns,
        resume_summary=session.resume_summary,
    )

    new_turn = InterviewTurn(turn_index=len(session.turns) + 1, question=next_q)
    session.turns.append(new_turn)
    update_session(session)

    return {
        "completed": False,
        "next_question": next_q,
        "turn_index": len(session.turns),
    }


@router.post("/camera-event")
def record_camera_event(req: CameraEventRequest) -> dict[str, str]:
    """Record browser-side visual coaching metrics during interview."""
    session = get_session(req.session_id)
    if session and session.status == "in_progress":
        session.camera_raw_events.append({
            "facing_camera": req.facing_camera,
            "good_posture": req.good_posture,
            "excessive_head_movement": req.excessive_head_movement,
        })
        update_session(session)
    return {"status": "ok"}


@router.post("/end")
def end_interview(session_id: str) -> dict[str, Any]:
    """Finalize interview session, run evaluation, detect skill gaps, and return report."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Interview session not found.")

    session.status = "completed"
    report = evaluate_interview_session(session)
    session.report = report
    
    detected_gaps = extract_skill_gaps(session)
    session.detected_skill_gaps = detected_gaps
    update_session(session)

    return {
        "session_id": session.session_id,
        "status": session.status,
        "report": report.model_dump(),
        "detected_skill_gaps": detected_gaps,
    }


@router.get("/report/{session_id}")
def get_report(session_id: str) -> dict[str, Any]:
    """Get completed interview report by session ID."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(404, "Interview session not found.")
    if not session.report:
        raise HTTPException(400, "Interview session report is not ready.")

    return {
        "session_id": session.session_id,
        "target_role": session.target_role,
        "interview_type": session.interview_type,
        "level": session.level,
        "created_at": session.created_at,
        "report": session.report.model_dump(),
        "detected_skill_gaps": session.detected_skill_gaps,
    }


@router.get("/history/{learner_id}")
def get_history(learner_id: str) -> dict[str, Any]:
    """Get history of completed interviews for learner."""
    history = get_learner_history(learner_id)
    
    summaries = []
    scores = []
    for s in history:
        if s.report:
            scores.append(s.report.overall_score)
            summaries.append({
                "session_id": s.session_id,
                "created_at": s.created_at,
                "target_role": s.target_role,
                "interview_type": s.interview_type,
                "overall_score": s.report.overall_score,
                "category_scores": s.report.category_scores,
                "detected_gaps_count": len(s.detected_skill_gaps),
            })

    # Calculate improvement trend deltas
    trend_deltas = {}
    if len(scores) >= 2:
        diff = scores[-1] - scores[0]
        trend_deltas["overall_growth"] = f"{'+' if diff >= 0 else ''}{round(diff, 1)}%"

    return {
        "learner_id": learner_id,
        "total_interviews": len(history),
        "history": summaries,
        "trend_deltas": trend_deltas,
    }


@router.post("/apply-gaps")
def apply_gaps(req: ApplyGapsRequest) -> dict[str, Any]:
    """Inject detected interview skill gaps into TESSA learner profile & update roadmap."""
    session = get_session(req.session_id)
    if not session or not session.detected_skill_gaps:
        # Generate gaps from session report if available
        if session and session.report:
            gaps = extract_skill_gaps(session)
        else:
            raise HTTPException(400, "No skill gaps found in interview session.")
    else:
        gaps = session.detected_skill_gaps

    result = apply_gaps_to_tessa_profile(req.learner_id, gaps)
    return result


@router.post("/jobs/match")
@jobs_router.post("/match")
def match_jobs(req: JobMatchRequest) -> dict[str, Any]:
    """Fetch live jobs from Adzuna / Tavily and calculate skills-based match %."""
    profile = store.get_profile(req.learner_id)
    raw_jobs = fetch_live_jobs(target_role=req.target_role, location=req.location)
    
    # Collect candidate skills from profile
    claimed = profile.claimed_skills
    known = [k.skill_id for k in profile.known_skills]
    user_skills = list(set(claimed + known))

    matched_jobs = []
    for j in raw_jobs:
        match_info = calculate_job_match(
            candidate_skills=user_skills,
            resume_summary={"skills": user_skills},
            job=j,
            target_role=req.target_role,
        )
        matched_jobs.append(match_info)

    # Sort descending by match percentage
    matched_jobs.sort(key=lambda x: x["match_percentage"], reverse=True)

    return {
        "target_role": req.target_role,
        "location": req.location,
        "total_jobs": len(matched_jobs),
        "jobs": matched_jobs,
    }
