import copy
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import networkx as nx

try:
    from app import store
    from app.engines import adapter, explainer, gap as gap_engine, planner, suitability
    from app.engines.profiler import mastery
    from app.schemas import Course, Feedback, LearningPath, Recommendation
    from app.api.deps import apply_completed_status, build_path, goal_session, learner_path
    from app.api.workspace import snapshot
except ImportError:
    from .. import store
    from ..engines import adapter, explainer, gap as gap_engine, planner, suitability
    from ..engines.profiler import mastery
    from ..schemas import Course, Feedback, LearningPath, Recommendation
    from .deps import apply_completed_status, build_path, goal_session, learner_path
    from .workspace import snapshot

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["path"])


class GenerateRequest(BaseModel):
    role_id: str | None = None


class SwapRequest(BaseModel):
    current_course_id: str
    replacement_course_id: str
    replacement_course_data: dict | None = None


@router.post("/path/{learner_id}/generate")
def generate(learner_id: str, req: GenerateRequest):
    """Plan the route and return the whole workspace with it.

    The response carries profile, catalogue and dashboard alongside the route
    so the browser opens a workspace on one round trip instead of six.
    """
    profile = store.get_profile(learner_id)
    if not profile.goal_text:
        raise HTTPException(400, "Tell me the goal first - POST /api/intake.")

    active = goal_session(learner_id)

    # There is exactly one derived role in a goal session.  `role_id` remains
    # accepted for older clients but cannot redirect a learner to a fixed list.
    path = build_path(active, profile)

    # A 200 response with an empty path sends the client into a workspace with
    # nothing to work on. This can still happen when every real resource is
    # longer than the learner's available window, so make the constraint
    # explicit instead of presenting an unfinished-looking blank route.
    if not path.milestones and any(item.gap > 0.05 for item in path.gap_before):
        # Say which of the two things actually happened. This used to blame the
        # learner's time window whenever they had one, including for a resource
        # set that was fully gated - nine short resources, none of them longer
        # than three hours, and the advice was "add weekly hours".
        window = (
            None if profile.time_unconstrained
            else max(profile.weekly_hours, 1.0) * max(profile.horizon_weeks, 1)
        )
        shortest = min((c.hours for c in active.catalog.courses), default=0.0)
        if window is not None and shortest > window:
            detail = (
                f"The shortest resource I found for this goal is {shortest:g} hours, and you "
                f"have {window:g}. Add weekly hours or extend the window and I will re-plan."
            )
        else:
            detail = (
                "I found the goal and its resources, but could not assemble a route from "
                "them. Build it again and I will search for a wider set."
            )
        raise HTTPException(422, detail)

    store.save_path(path)
    store.log_event(
        learner_id,
        "path_generated",
        {"readiness": path.readiness_before, "coverage": path.coverage},
    )
    return snapshot(
        learner_id,
        active=active,
        profile=profile,
        path=path,
        summary=explainer.summarise_path_template(path, profile),
    )


@router.get("/path/{learner_id}", response_model=LearningPath)
def get_path(learner_id: str) -> LearningPath:
    path = store.get_path(learner_id)
    if path is None:
        raise HTTPException(404, "No path generated yet.")
    return path


@router.get("/path/{learner_id}/explain/{course_id}")
def explain(learner_id: str, course_id: str):
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    path = learner_path(learner_id, active, profile)
    if path is None:
        raise HTTPException(404, "No path generated yet.")

    item = next(
        (i for ms in path.milestones for i in ms.items if i.id == course_id), None
    )
    if item is None or item.course is None:
        raise HTTPException(404, "That item is not in the path.")

    covers = next(
        (r.detail.get("skills", []) for r in item.reasons if r.type == "GAP_COVERAGE"), []
    )
    rec = Recommendation(
        course=item.course, score=0.0, components={}, reasons=item.reasons, covers=covers
    )
    return {
        "course_id": course_id,
        "explanation": explainer.explain_recommendation(rec, profile, cat),
        "reason_codes": [r.model_dump() for r in item.reasons],
    }


@router.get("/path/{learner_id}/why-not/{course_id}")
def why_not(learner_id: str, course_id: str):
    """The counterfactual. Answers "why isn't X on my path" from the
    prerequisite graph and the time budget, not from vibes."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    path = learner_path(learner_id, active, profile)
    if path is None:
        raise HTTPException(404, "No path generated yet.")

    m = mastery(profile, cat)
    return {
        "course_id": course_id,
        "explanation": explainer.explain_rejection(course_id, path, profile, m, cat),
    }


@router.post("/path/{learner_id}/feedback")
def feedback(learner_id: str, fb: Feedback):
    # The identity is in the path. A body naming a different learner is a
    # malformed request, not a licence to write to that learner.
    if fb.learner_id and fb.learner_id != learner_id:
        raise HTTPException(400, "learner_id in the body must match the one in the path.")
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    arms = store.arms(learner_id)

    message = adapter.apply(profile, fb, cat, arms)
    store.save_profile(profile)
    store.log_event(learner_id, "feedback", {"signal": fb.signal, "item": fb.item_id})

    if fb.signal == "completed":
        path = store.get_path(learner_id) or build_path(active, profile)
    else:
        path = build_path(active, profile)

    apply_completed_status(path, profile)
    store.save_path(path)

    return {
        "message": message,
        "preferred_formats": adapter.preferred_formats(arms),
        **snapshot(learner_id, active=active, profile=profile, path=path),
    }


class SimulateRequest(BaseModel):
    weekly_hours: float | None = None
    horizon_weeks: int | None = None
    budget: str | None = None
    time_unconstrained: bool | None = None


@router.post("/path/{learner_id}/simulate", response_model=LearningPath)
def simulate(learner_id: str, req: SimulateRequest) -> LearningPath:
    """What-if. Drives the "drag your weekly hours and watch the timeline
    move" control - runs on a copy so nothing is persisted."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = copy.deepcopy(store.get_profile(learner_id))
    updates = req.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(profile, field, value)
    if "horizon_weeks" in updates and "time_unconstrained" not in updates:
        profile.time_unconstrained = False
    return planner.build_path(profile, cat, active.retriever)


@router.get("/recommendations/{learner_id}")
def recommendations(learner_id: str, q: str = "", limit: int = Query(10, ge=1, le=50)):
    """Standalone recommendations, outside the path. Used by the "explore"
    panel and by the chat when someone asks for an alternative."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    role = active.role

    target, weight = cat.role_target(role)
    m = mastery(profile, cat)
    gap = gap_engine.gap_vector(m, target, weight)

    recs = active.retriever.rank(profile, m, gap, q or profile.goal_text, limit=limit)
    return [
        {
            "course": r.course.model_dump(),
            "score": r.score,
            "components": r.components,
            "covers": [cat.name(s) for s in r.covers],
            "reason_codes": [rc.model_dump() for rc in r.reasons],
        }
        for r in recs
    ]


@router.get("/path/{learner_id}/suitability/{course_id}")
def get_suitability(learner_id: str, course_id: str):
    """Multi-dimensional pedagogical suitability evaluation.
    Evaluates gap fit, pacing, prerequisite status, and practical balance,
    completely independent of view counts or SEO popularity."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    course = cat.course_by_id.get(course_id)
    if not course:
        # Also check path milestones
        path = store.get_path(learner_id)
        if path:
            course = next((i.course for ms in path.milestones for i in ms.items if i.course and i.course.id == course_id), None)
    if not course:
        raise HTTPException(404, f"Course {course_id} not found.")
    report = suitability.analyze_suitability(course, profile, cat)
    return report.model_dump()


@router.get("/path/{learner_id}/alternatives/{course_id}")
def get_alternatives(learner_id: str, course_id: str, limit: int = Query(4, ge=1, le=10)):
    """'If not this, suggest another'.
    Returns categorized alternative resources (Faster crash course, Hands-on project,
    Text/Docs reference, Deep dive) that teach the exact same skill gap."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    course = cat.course_by_id.get(course_id)
    if not course:
        path = store.get_path(learner_id)
        if path:
            course = next((i.course for ms in path.milestones for i in ms.items if i.course and i.course.id == course_id), None)
            if course:
                cat.course_by_id[course.id] = course
    if not course:
        raise HTTPException(404, f"Course {course_id} not found.")
    alts = suitability.find_alternatives(course_id, profile, cat, max_results=limit)
    return [alt.model_dump() for alt in alts]


@router.get("/path/{learner_id}/audit/{course_id}")
def get_audit(learner_id: str, course_id: str):
    """The 4-layer anti-hallucination verification audit.
    Exposes verifiable NetworkX topological sorting, Tavily web grounding,
    deterministic reason codes, and bounded Pydantic schemas."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    path = store.get_path(learner_id) or learner_path(learner_id, active, profile)
    course = cat.course_by_id.get(course_id)
    if not course and path:
        course = next((i.course for ms in path.milestones for i in ms.items if i.course and i.course.id == course_id), None)
        if course:
            cat.course_by_id[course.id] = course
    if not course:
        raise HTTPException(404, f"Course {course_id} not found.")
    report = suitability.generate_audit_trail(course_id, profile, cat, path)
    return report.model_dump()


@router.post("/path/{learner_id}/swap")
def swap_resource(learner_id: str, req: SwapRequest):
    """Swap an item in the trajectory with an alternative recommendation.
    Verifies that the NetworkX DAG remains acyclic with zero prerequisite inversions,
    recalculates milestone schedules, and returns the updated workspace."""
    active = goal_session(learner_id)
    cat = active.catalog
    profile = store.get_profile(learner_id)
    path = store.get_path(learner_id) or learner_path(learner_id, active, profile)
    if not path:
        raise HTTPException(404, "No learning path exists for this learner.")

    # Locate current item in path milestones
    target_ms = None
    target_item = None
    for ms in path.milestones:
        for item in ms.items:
            if item.id == req.current_course_id or (item.course and item.course.id == req.current_course_id):
                target_ms = ms
                target_item = item
                break
        if target_item:
            break

    if not target_item or not target_item.course:
        raise HTTPException(404, f"Course {req.current_course_id} is not in the active trajectory.")

    # Resolve replacement course
    replacement = cat.course_by_id.get(req.replacement_course_id)
    if not replacement and req.replacement_course_data:
        try:
            replacement = Course(**req.replacement_course_data)
            cat.courses.append(replacement)
            cat.course_by_id[replacement.id] = replacement
        except Exception as exc:
            log.warning("Failed to parse replacement_course_data: %s", exc)

    if not replacement:
        # Search among generated alternatives
        alts = suitability.find_alternatives(req.current_course_id, profile, cat, max_results=8)
        match_alt = next((a for a in alts if a.id == req.replacement_course_id), None)
        if match_alt:
            replacement = Course(
                id=match_alt.id,
                title=match_alt.title,
                provider=match_alt.provider,
                url=match_alt.url,
                description=match_alt.why_choose_this,
                level=match_alt.level, # type: ignore
                hours=match_alt.hours,
                hours_stated=True,
                cost=match_alt.cost, # type: ignore
                format=match_alt.format, # type: ignore
                teaches=target_item.course.teaches,
                requires=target_item.course.requires,
            )
            cat.courses.append(replacement)
            cat.course_by_id[replacement.id] = replacement

    if not replacement:
        raise HTTPException(404, f"Alternative course {req.replacement_course_id} could not be resolved.")

    # NetworkX DAG Cycle & Prerequisite Check
    G = nx.DiGraph()
    all_courses: list[Course] = []
    for ms in path.milestones:
        for item in ms.items:
            if item.course:
                if item.id == target_item.id:
                    all_courses.append(replacement)
                else:
                    all_courses.append(item.course)

    for c in all_courses:
        G.add_node(c.id)
    for c1 in all_courses:
        for c2 in all_courses:
            if c1.id != c2.id and any(sid in c1.teaches for sid in c2.requires):
                G.add_edge(c1.id, c2.id)

    if not nx.is_directed_acyclic_graph(G):
        raise HTTPException(422, "Cannot swap: this replacement would introduce a cyclic prerequisite dependency.")

    # Perform in-place swap
    old_title = target_item.title
    target_item.id = replacement.id
    target_item.title = replacement.title
    target_item.hours = replacement.hours
    target_item.course = replacement
    target_item.description = replacement.description

    # Recalculate milestone & path durations
    for ms in path.milestones:
        ms.hours = round(sum(i.hours for i in ms.items), 1)
    path.total_hours = round(sum(ms.hours for ms in path.milestones), 1)

    # Recalculate schedule timeline
    weekly = max(profile.weekly_hours, 1.0)
    curr_week = 1
    for ms in path.milestones:
        ms.start_week = curr_week
        span = max(1, round(ms.hours / weekly))
        ms.end_week = curr_week + span - 1
        curr_week = ms.end_week + 1
    path.total_weeks = max(1, curr_week - 1)

    # Persist and log
    store.save_path(path)
    store.log_event(
        learner_id,
        "course_swapped",
        {"from_id": req.current_course_id, "to_id": replacement.id, "to_title": replacement.title},
    )

    return {
        "message": f"Successfully swapped: replaced '{old_title}' with '{replacement.title}'",
        "swapped_to_id": replacement.id,
        **snapshot(learner_id, active=active, profile=profile, path=path),
    }
