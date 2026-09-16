"""Skill gap detection and integration with TESSA Learner Profile & Planner."""

from __future__ import annotations

import logging
from typing import Any
from .. import store
from .session import InterviewSession

log = logging.getLogger(__name__)


def extract_skill_gaps(session: InterviewSession) -> list[dict[str, Any]]:
    """Convert interview evaluation report into structured skill gaps."""
    report = session.report
    if not report:
        return []

    gaps = []
    # Process needs_improvement & missed_concepts
    weak_items = report.needs_improvement + report.missed_concepts

    for item in weak_items:
        clean_name = item.strip()
        if not clean_name:
            continue
        
        # Calculate current proficiency from actual performance
        score = report.category_scores.get("Technical Knowledge", report.overall_score)
        current_pct = max(min(int(score * 0.6), 55), 0)

        gaps.append({
            "skill_name": clean_name,
            "current_percentage": current_pct,
            "target_percentage": 85,
            "status": "weak" if current_pct < 45 else "needs_improvement",
        })

    return gaps


def apply_gaps_to_tessa_profile(learner_id: str, gaps: list[dict[str, Any]]) -> dict[str, Any]:
    """Inject detected interview skill gaps into TESSA learner profile & clear cached path.
    
    This forces the existing TESSA roadmap planner engine to generate an updated
    prerequisite-locked route specifically covering these weak skills.
    """
    profile = store.get_profile(learner_id)
    
    added_names = []
    for gap in gaps:
        name = gap.get("skill_name")
        if not name:
            continue
        added_names.append(name)
        # Append as claimed skill or update goal_text context
        if name not in profile.claimed_skills:
            profile.claimed_skills.append(name)

    # Append weak skills to goal text if profile has existing goal
    if profile.goal_text:
        weak_summary = ", ".join(added_names[:4])
        if "Focus areas:" not in profile.goal_text:
            profile.goal_text += f" (Focus areas: {weak_summary})"

    # Clear cached learning path so next generate call builds a fresh route targeting gaps
    store.clear_path(learner_id)
    store.save_profile(profile)

    return {
        "success": True,
        "learner_id": learner_id,
        "gaps_applied": len(added_names),
        "applied_skills": added_names,
        "message": f"Successfully applied {len(added_names)} skill gaps to TESSA profile. Roadmap is ready for update.",
    }
