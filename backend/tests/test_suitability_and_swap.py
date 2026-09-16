"""Test pedagogical suitability scoring, alternative recommendations, swap engine, and anti-hallucination audit."""

from fastapi.testclient import TestClient

from app import session, store
from app.catalog import Catalog
from app.engines import suitability
from app.main import app
from app.schemas import Course, LearnerProfile, LearningPath, Milestone, PathItem, Role, Skill

GOAL_TEXT = "Become a research data analyst who can turn messy data into clear decisions."
LEARNER = "suitability-test-learner"


def test_suitability_scoring():
    skill = Skill(id="py.basics", name="Python Basics", domain="programming")
    course = Course(
        id="c_python_intro",
        title="Python for Absolute Beginners Full Course",
        provider="freeCodeCamp.org",
        url="https://www.youtube.com/watch?v=rfscVS0vtbw",
        description="Comprehensive beginner course covering syntax, loops, functions, and data structures.",
        level="beginner",
        hours=4.5,
        hours_stated=True,
        cost="free",
        format="video",
        teaches={"py.basics": 0.8},
        requires={},
    )
    cat = Catalog([skill], [course], [Role(id="r1", title="Python Dev", requirements={"py.basics": {"level": 0.8, "weight": 1.0}})])
    profile = LearnerProfile(learner_id="p1", weekly_hours=6.0, budget="free")

    report = suitability.analyze_suitability(course, profile, cat)
    assert report.match_score >= 85
    assert report.zero_view_bias is True
    assert "Python Basics" in report.pedagogical_headline or "Python Basics" in report.gap_coverage_summary
    assert "4.5 hours" in report.pacing_fit


def test_alternatives_generation():
    skill = Skill(id="py.basics", name="Python Basics", domain="programming")
    course1 = Course(
        id="c_python_long",
        title="Complete Python Masterclass 2026",
        provider="YouTube",
        url="https://www.youtube.com/watch?v=abcdef12345",
        description="Complete multi-hour guide to Python.",
        level="beginner",
        hours=10.0,
        hours_stated=True,
        cost="free",
        format="video",
        teaches={"py.basics": 0.8},
        requires={},
    )
    course2 = Course(
        id="c_python_fast",
        title="Python Crash Course in 1 Hour",
        provider="YouTube",
        url="https://www.youtube.com/watch?v=xyz98765432",
        description="Fast-paced quick summary of syntax.",
        level="beginner",
        hours=1.5,
        hours_stated=True,
        cost="free",
        format="video",
        teaches={"py.basics": 0.7},
        requires={},
    )
    cat = Catalog([skill], [course1, course2], [])
    profile = LearnerProfile(learner_id="p1", weekly_hours=5.0)

    alts = suitability.find_alternatives("c_python_long", profile, cat, max_results=3)
    assert len(alts) >= 1
    # Check that trade off label exists
    assert any(alt.trade_off_label for alt in alts)
    assert all(alt.replaces_course_id == "c_python_long" for alt in alts)


def test_audit_trail_generation():
    skill = Skill(id="py.basics", name="Python Basics", domain="programming")
    course = Course(
        id="c_python_video",
        title="Python for Absolute Beginners",
        provider="YouTube",
        url="https://www.youtube.com/watch?v=rfscVS0vtbw",
        description="Introductory Python tutorial.",
        level="beginner",
        hours=4.0,
        hours_stated=True,
        cost="free",
        format="video",
        teaches={"py.basics": 0.8},
        requires={},
    )
    cat = Catalog([skill], [course], [])
    profile = LearnerProfile(learner_id="p1")

    audit = suitability.generate_audit_trail("c_python_video", profile, cat)
    assert audit.url_verified is True
    assert "0.0%" in audit.hallucination_risk
    assert "TESSA-AUDIT-" in audit.verification_hash
    assert "YouTube" in audit.provenance


if __name__ == "__main__":
    print("Running test_suitability_scoring...")
    test_suitability_scoring()
    print("PASS")

    print("Running test_alternatives_generation...")
    test_alternatives_generation()
    print("PASS")

    print("Running test_audit_trail_generation...")
    test_audit_trail_generation()
    print("PASS")
    print("All unit tests passed successfully!")
