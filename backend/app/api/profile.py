from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import session, store
from ..engines import diagnostic, intake
from ..engines.profiler import mastery
from ..schemas import Cost, Fmt, LearnerProfile, SkillClaim
from .deps import goal_session

router = APIRouter(prefix="/api", tags=["profile"])

# Diagnostics are regenerated per request but the question text is cached in
# llm.py, so this is only here to keep the correct answers server-side.


class IntakeRequest(BaseModel):
    learner_id: str
    message: str


class IntakeResponse(BaseModel):
    profile: LearnerProfile
    follow_up_question: str | None = None
    confidence: float
    ready: bool


@router.post("/intake", response_model=IntakeResponse)
def intake_turn(req: IntakeRequest) -> IntakeResponse:
    profile = store.get_profile(req.learner_id)

    history = [f"{h['role']}: {h['content']}" for h in store.history(req.learner_id)]
    previous_goal = profile.goal_text
    previous_budget = profile.budget
    planning_before = _planning_signature(profile)
    draft = intake.extract(req.message, history, existing_goal=previous_goal)

    # A graph, its resource ids, and measured answers belong to one goal. Do
    # not accidentally carry any of them into a different learner intention.
    if draft.goal_text and draft.goal_text != previous_goal:
        session.drop(req.learner_id)
        store.clear_path(req.learner_id)
        profile.target_role = None
        profile.known_skills.clear()
        profile.claimed_skills.clear()
        profile.completed_courses.clear()
        profile.rejected_courses.clear()
        profile.quiz_results.clear()
    elif _planning_signature(profile) != planning_before:
        store.clear_path(req.learner_id)
        if profile.budget != previous_budget:
            session.drop(req.learner_id)

    profile = intake.merge(profile, draft)
    store.save_profile(profile)

    store.append_history(req.learner_id, "user", req.message)
    if draft.follow_up_question:
        store.append_history(req.learner_id, "assistant", draft.follow_up_question)

    ready = bool(profile.goal_text) and draft.confidence >= 0.7
    return IntakeResponse(
        profile=profile,
        follow_up_question=draft.follow_up_question,
        confidence=draft.confidence,
        ready=ready,
    )


@router.get("/profile/{learner_id}", response_model=LearnerProfile)
def get_profile(learner_id: str) -> LearnerProfile:
    return store.get_profile(learner_id)


class ProfilePatch(BaseModel):
    """The write surface for a profile.

    LearnerProfile constrains these fields; the patch that writes to it did
    not, so the API accepted a zero-week horizon or negative weekly hours that
    the planner then had to divide by.
    """

    goal_text: str | None = Field(default=None, max_length=2000)
    target_role: str | None = None
    weekly_hours: float | None = Field(default=None, gt=0, le=80)
    horizon_weeks: int | None = Field(default=None, ge=1, le=260)
    time_unconstrained: bool | None = None
    budget: Cost | None = None
    format_prefs: list[Fmt] | None = None
    known_skills: list[SkillClaim] | None = None
    completed_courses: list[str] | None = None
    custom_milestones: list[dict] | None = None
    milestone_deadlines: dict[str, str] | None = None
    current_streak: int | None = None
    longest_streak: int | None = None
    last_active_date: str | None = None
    activity_history: list[str] | None = None
    daily_goal_minutes: int | None = None
    streak_freeze_count: int | None = None


def _planning_signature(profile: LearnerProfile) -> tuple:
    """Fields whose changes make an already stored route stale."""
    return (
        profile.weekly_hours,
        profile.horizon_weeks,
        profile.time_unconstrained,
        profile.budget,
        tuple(profile.format_prefs),
        tuple(profile.claimed_skills),
        tuple((claim.skill_id, claim.self_rating) for claim in profile.known_skills),
        tuple(profile.completed_courses),
    )


@router.patch("/profile/{learner_id}", response_model=LearnerProfile)
def patch_profile(learner_id: str, patch: ProfilePatch) -> LearnerProfile:
    """The chat is the headline interface but nobody wants to type
    'actually make it 8 hours a week' - the dashboard edits land here."""
    profile = store.get_profile(learner_id)
    old_goal, old_budget = profile.goal_text, profile.budget
    planning_before = _planning_signature(profile)
    updates = patch.model_dump(exclude_none=True)
    for field, value in updates.items():
        if field == "target_role":
            continue
        setattr(profile, field, value)
    if "horizon_weeks" in updates and "time_unconstrained" not in updates:
        profile.time_unconstrained = False

    # `target_role` is retained as a wire-format compatibility field, but it
    # is derived from the goal graph and must never select a hidden static role.
    goal_changed = profile.goal_text != old_goal
    if goal_changed:
        profile.target_role = None
        profile.known_skills.clear()
        profile.claimed_skills.clear()
        profile.completed_courses.clear()
        profile.rejected_courses.clear()
        profile.quiz_results.clear()

    if goal_changed or profile.budget != old_budget:
        session.drop(learner_id)

    if goal_changed or _planning_signature(profile) != planning_before:
        store.clear_path(learner_id)

    store.save_profile(profile)
    return profile


@router.get("/profile/{learner_id}/diagnostic")
def get_diagnostic(learner_id: str):
    active = goal_session(learner_id)   # also snaps stated skills onto the graph
    cat = active.catalog
    profile = store.get_profile(learner_id)
    role = active.role

    target, weight = cat.role_target(role)
    items = diagnostic.build(profile, target, weight, cat)
    store.save_quiz(learner_id, [i.model_dump(mode="json") for i in items])

    return {
        "role": role.title,
        "questions": [
            {
                "skill_id": i.skill_id,
                "skill_name": i.skill_name,
                "question": i.question,
                "options": i.options,
            }
            for i in items
        ],
    }


class DiagnosticAnswers(BaseModel):
    answers: dict[str, int]   # skill_id -> chosen option index


@router.post("/profile/{learner_id}/diagnostic")
def submit_diagnostic(learner_id: str, payload: DiagnosticAnswers):
    # Held in the shared store rather than in this process: the instance that
    # built the paper is often not the one that receives the answers.
    items = [diagnostic.QuizItem(**row) for row in store.take_quiz(learner_id)]
    if not items:
        raise HTTPException(400, "No diagnostic in progress - request one first.")

    cat = goal_session(learner_id).catalog
    profile = store.get_profile(learner_id)
    before = mastery(profile, cat)

    # grade() already returns the observed mastery per skill, and the profiler
    # blends quiz_results against the priors. Nudging the same answers a second
    # time here was double-counting them.
    scored = diagnostic.grade(items, payload.answers)
    profile.quiz_results.update(scored)
    store.save_profile(profile)

    after = mastery(profile, cat)
    moved = [
        {
            "skill_id": s.id,
            "skill_name": s.name,
            "before": round(float(before[i]), 2),
            "after": round(float(after[i]), 2),
        }
        for i, s in enumerate(cat.skills)
        if abs(float(after[i] - before[i])) > 0.05
    ]
    store.log_event(learner_id, "diagnostic", {"skills_moved": len(moved)})

    return {"scored": scored, "changed": moved, "profile": profile}


# --------------------------------------------------------------------------
# Working Milestone Feature Endpoints
# --------------------------------------------------------------------------

class MilestoneTargetRequest(BaseModel):
    milestone_index: int
    target_date: str | None = None
    custom_goal: str | None = None


@router.post("/profile/{learner_id}/milestone-target")
def set_milestone_target(learner_id: str, req: MilestoneTargetRequest):
    """Set target deadline and optional goal for a specific learning path milestone."""
    profile = store.get_profile(learner_id)
    if req.target_date is not None:
        profile.milestone_deadlines[str(req.milestone_index)] = req.target_date

    import uuid
    if req.custom_goal:
        profile.custom_milestones.append({
            "id": f"cms_{uuid.uuid4().hex[:8]}",
            "milestone_index": req.milestone_index,
            "goal": req.custom_goal.strip(),
            "target_date": req.target_date or "",
            "done": False,
        })
    store.save_profile(profile)

    # Sync with path milestones if generated
    path = store.get_path(learner_id)
    if path:
        from datetime import date
        for ms in path.milestones:
            if ms.index == req.milestone_index and req.target_date:
                try:
                    ms.target_date = date.fromisoformat(req.target_date)
                except Exception:
                    pass
        store.save_path(path)

    store.log_event(
        learner_id,
        "milestone_target_set",
        {"milestone_index": req.milestone_index, "target_date": req.target_date},
    )
    return {
        "status": "ok",
        "message": f"Deadline updated for Phase {req.milestone_index}",
        "milestone_deadlines": profile.milestone_deadlines,
        "custom_milestones": profile.custom_milestones,
    }


class CustomMilestoneCreate(BaseModel):
    goal: str
    target_date: str | None = None
    milestone_index: int = 1


@router.post("/profile/{learner_id}/custom-milestone")
def add_custom_milestone(learner_id: str, req: CustomMilestoneCreate):
    """Add a personal milestone checkpoint / learning goal to My Profile."""
    profile = store.get_profile(learner_id)
    import uuid
    entry = {
        "id": f"cms_{uuid.uuid4().hex[:8]}",
        "milestone_index": req.milestone_index,
        "goal": req.goal.strip(),
        "target_date": req.target_date or "",
        "done": False,
    }
    profile.custom_milestones.append(entry)
    store.save_profile(profile)
    store.log_event(learner_id, "custom_milestone_added", {"goal": req.goal})
    return {"status": "ok", "custom_milestones": profile.custom_milestones, "added": entry}


@router.post("/profile/{learner_id}/custom-milestone/{item_id}/toggle")
def toggle_custom_milestone(learner_id: str, item_id: str):
    """Toggle completion of a personal milestone target."""
    profile = store.get_profile(learner_id)
    target = None
    for m in profile.custom_milestones:
        if m.get("id") == item_id:
            m["done"] = not m.get("done", False)
            target = m
            break
    store.save_profile(profile)
    return {"status": "ok", "custom_milestones": profile.custom_milestones, "toggled": target}


@router.delete("/profile/{learner_id}/custom-milestone/{item_id}")
def delete_custom_milestone(learner_id: str, item_id: str):
    """Remove a personal milestone goal."""
    profile = store.get_profile(learner_id)
    profile.custom_milestones = [m for m in profile.custom_milestones if m.get("id") != item_id]
    store.save_profile(profile)
    return {"status": "ok", "custom_milestones": profile.custom_milestones}


@router.post("/profile/{learner_id}/complete-milestone/{milestone_index}")
def complete_entire_milestone(learner_id: str, milestone_index: int):
    """Complete all items in a milestone phase directly from My Profile and re-plan route."""
    profile = store.get_profile(learner_id)
    path = store.get_path(learner_id)
    if not path:
        raise HTTPException(404, "No active learning path found.")

    target_ms = next((m for m in path.milestones if m.index == milestone_index), None)
    if not target_ms:
        raise HTTPException(404, f"Milestone {milestone_index} not found.")

    newly_completed = 0
    for item in target_ms.items:
        if item.kind == "course":
            if item.id not in profile.completed_courses:
                profile.completed_courses.append(item.id)
                newly_completed += 1
        if item.id not in profile.completed_items:
            profile.completed_items.append(item.id)
        item.status = "done"

    store.save_profile(profile)
    store.save_path(path)
    store.log_event(
        learner_id,
        "milestone_completed",
        {"milestone_index": milestone_index, "title": target_ms.title, "items": newly_completed},
    )

    from .deps import apply_completed_status, build_path, goal_session
    from .workspace import snapshot
    active = goal_session(learner_id)
    new_path = build_path(active, profile)
    apply_completed_status(new_path, profile)
    store.save_path(new_path)

    return {
        "status": "ok",
        "message": f"Successfully completed Phase {milestone_index}: {target_ms.title}!",
        "milestone_index": milestone_index,
        **snapshot(learner_id, active=active, profile=profile, path=new_path),
    }


class CheckInRequest(BaseModel):
    minutes: int = 45
    note: str = ""
    date: str | None = None


@router.post("/profile/{learner_id}/check-in")
def check_in(learner_id: str, req: CheckInRequest = CheckInRequest()):
    """Log a study session / daily check-in to advance or maintain the study streak."""
    from datetime import date, datetime

    profile = store.get_profile(learner_id)
    today = req.date or date.today().isoformat()

    last_active = profile.last_active_date
    current = profile.current_streak or 0
    longest = profile.longest_streak or 0
    freezes = profile.streak_freeze_count

    message = ""
    freeze_used = False

    if not last_active:
        current = 1
        message = "First study session logged! 1-day streak started 🔥"
    elif last_active == today:
        message = "You've already checked in today! Great dedication 🚀"
    else:
        try:
            d_last = datetime.strptime(last_active, "%Y-%m-%d").date()
            d_today = datetime.strptime(today, "%Y-%m-%d").date()
            diff = (d_today - d_last).days
        except Exception:
            diff = 1

        if diff == 1:
            current += 1
            message = f"Streak increased! {current}-day study streak 🔥"
        elif diff == 2 and freezes > 0:
            freezes -= 1
            freeze_used = True
            current += 1
            message = f"Streak Shield saved your streak! Now on {current}-day streak 🛡️🔥"
        elif diff > 1:
            current = 1
            message = "New streak started! 1-day streak 🔥"

    longest = max(longest, current)
    profile.current_streak = current
    profile.longest_streak = longest
    profile.last_active_date = today
    profile.streak_freeze_count = freezes

    if today not in profile.activity_history:
        profile.activity_history.append(today)

    store.save_profile(profile)
    store.log_event(
        learner_id,
        "study_check_in",
        {
            "date": today,
            "minutes": req.minutes,
            "current_streak": current,
            "freeze_used": freeze_used,
        },
    )

    return {
        "status": "ok",
        "message": message,
        "current_streak": current,
        "longest_streak": longest,
        "last_active_date": today,
        "activity_history": profile.activity_history,
        "streak_freeze_count": profile.streak_freeze_count,
        "daily_goal_minutes": profile.daily_goal_minutes,
        "freeze_used": freeze_used,
    }


class StreakTargetRequest(BaseModel):
    daily_goal_minutes: int = Field(ge=5, le=480)


@router.post("/profile/{learner_id}/streak-target")
def set_streak_target(learner_id: str, req: StreakTargetRequest):
    """Set the learner's daily study habit target in minutes."""
    profile = store.get_profile(learner_id)
    profile.daily_goal_minutes = req.daily_goal_minutes
    store.save_profile(profile)
    return {
        "status": "ok",
        "daily_goal_minutes": profile.daily_goal_minutes,
        "message": f"Daily habit target set to {req.daily_goal_minutes} mins/day 🎯",
    }


@router.post("/profile/{learner_id}/streak-freeze")
def add_streak_freeze(learner_id: str):
    """Equip or claim a streak freeze shield (max 2)."""
    profile = store.get_profile(learner_id)
    if profile.streak_freeze_count < 2:
        profile.streak_freeze_count += 1
        store.save_profile(profile)
        msg = "Streak Freeze Shield equipped! 🛡️"
    else:
        msg = "Maximum streak freeze shields (2) already active 🛡️"
    return {
        "status": "ok",
        "streak_freeze_count": profile.streak_freeze_count,
        "message": msg,
    }

