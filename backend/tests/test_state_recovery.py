"""The deployed failure: a request answered by a process that never saw the learner.

Vercel spreads one learner's requests over several instances, each with its own
memory and its own /tmp. Before this, the second request of a session could land
on an instance where ``store`` was empty and the session died with "No goal to
work from yet" - reproduced live against the deployment, on the first click of a
mission profile.

Here a cold instance is simulated by clearing the store between requests while
the browser keeps its copy of the profile, exactly as the real client does.
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app import session, store
from app.main import app
from app.schemas import LearnerProfile
from tests.conftest import GOAL_TEXT

LEARNER = "cold-instance-learner"


def _header(profile: dict) -> dict[str, str]:
    """Encode a profile the way the browser does."""
    import json

    raw = json.dumps(profile).encode("utf-8")
    return {"x-tessa-profile": base64.b64encode(raw).decode("ascii")}


def _go_cold() -> None:
    """Forget everything, as a request landing on another instance would find."""
    for mapping in (store._profiles, store._paths, store._arms, store._history,
                    store._events, store._quizzes):
        mapping.clear()


def test_generate_survives_a_cold_instance(install_session):
    with TestClient(app) as client:
        intake = client.post(
            "/api/intake",
            json={
                "learner_id": LEARNER,
                "message": GOAL_TEXT + " I know basic Python, can study 8 hours a week for 20 weeks.",
            },
        )
        profile = intake.json()["profile"]
        install_session(LEARNER, profile["goal_text"], profile["budget"])

        _go_cold()

        generated = client.post(
            f"/api/path/{LEARNER}/generate", json={}, headers=_header(profile)
        )

    assert generated.status_code == 200, generated.json()
    assert generated.json()["path"]["milestones"]


def test_workspace_survives_a_cold_instance(install_session):
    with TestClient(app) as client:
        intake = client.post(
            "/api/intake",
            json={
                "learner_id": LEARNER,
                "message": GOAL_TEXT + " I know basic Python, can study 8 hours a week for 20 weeks.",
            },
        )
        profile = intake.json()["profile"]
        install_session(LEARNER, profile["goal_text"], profile["budget"])
        client.post(f"/api/path/{LEARNER}/generate", json={})

        _go_cold()
        install_session(LEARNER, profile["goal_text"], profile["budget"])

        # No stored path on this instance either: the route is replanned from
        # the adopted profile rather than reported as missing progress.
        snapshot = client.get(f"/api/workspace/{LEARNER}", headers=_header(profile))

    assert snapshot.status_code == 200, snapshot.json()
    body = snapshot.json()
    assert body["path"]["milestones"]
    assert body["catalog"]["courses"] and body["catalog"]["skills"]
    assert body["dashboard"]["progress"]["items_total"] > 0


def test_without_the_header_a_cold_instance_still_fails_honestly(install_session):
    """The header is the fix; nothing else silently invents a goal."""
    with TestClient(app) as client:
        client.post(
            "/api/intake",
            json={"learner_id": LEARNER, "message": GOAL_TEXT + " 8 hours a week for 20 weeks."},
        )
        install_session(LEARNER)
        _go_cold()
        session.drop(LEARNER)
        response = client.post(f"/api/path/{LEARNER}/generate", json={})

    assert response.status_code == 400
    assert "goal" in response.json()["detail"].lower()


def test_adopt_never_moves_state_backwards():
    _go_cold()
    ahead = LearnerProfile(learner_id="rev-learner", goal_text="learn to sail", rev=4)
    store.adopt(ahead)

    stale = LearnerProfile(learner_id="rev-learner", goal_text="learn to ski", rev=2)
    assert store.adopt(stale) is False
    assert store.get_profile("rev-learner").goal_text == "learn to sail"

    newer = LearnerProfile(learner_id="rev-learner", goal_text="learn to ski", rev=5)
    assert store.adopt(newer) is True
    assert store.get_profile("rev-learner").goal_text == "learn to ski"


def test_save_profile_advances_the_revision():
    _go_cold()
    profile = store.get_profile("rev-bump-learner")
    before = profile.rev
    store.save_profile(profile)
    assert store.get_profile("rev-bump-learner").rev == before + 1


def test_a_malformed_header_is_ignored_not_fatal():
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"x-tessa-profile": "not-base64-at-all"})
    assert response.status_code == 200


def test_chat_survives_a_cold_instance(install_session):
    """Chat streams, so it does not go through the shared request wrapper.

    It sent no profile header at all, which meant a perfectly valid route
    could answer 503 on the request that happened to land on a fresh
    instance - intermittently, which is the worst way to fail.
    """
    with TestClient(app) as client:
        intake = client.post(
            "/api/intake",
            json={
                "learner_id": LEARNER,
                "message": GOAL_TEXT + " I know basic Python, can study 8 hours a week for 20 weeks.",
            },
        )
        profile = intake.json()["profile"]
        install_session(LEARNER, profile["goal_text"], profile["budget"])
        client.post(f"/api/path/{LEARNER}/generate", json={}, headers=_header(profile))

        _go_cold()

        answered = client.post(
            "/api/chat",
            json={"learner_id": LEARNER, "message": "what should I do first?", "history": []},
            headers=_header(profile),
        )

    assert answered.status_code == 200, answered.text


def test_a_diagnostic_is_graded_by_whichever_instance_receives_it(install_session):
    """The paper costs a model call per question, so it cannot be re-derived.

    Holding it in a module-level dict meant the instance that received the
    answers usually had no idea a diagnostic was in progress.
    """
    with TestClient(app) as client:
        intake = client.post(
            "/api/intake",
            json={
                "learner_id": LEARNER,
                "message": GOAL_TEXT + " I know basic Python, can study 8 hours a week for 20 weeks.",
            },
        )
        profile = intake.json()["profile"]
        install_session(LEARNER, profile["goal_text"], profile["budget"])

        quiz = client.get(f"/api/profile/{LEARNER}/diagnostic", headers=_header(profile))
        assert quiz.status_code == 200, quiz.text
        questions = quiz.json()["questions"]
        assert questions

        pending = dict(store._quizzes)
        _go_cold()
        store._quizzes.update(pending)   # durable storage survives; memory does not

        graded = client.post(
            f"/api/profile/{LEARNER}/diagnostic",
            json={"answers": {q["skill_id"]: 1 for q in questions}},
            headers=_header(profile),
        )

    assert graded.status_code == 200, graded.text
