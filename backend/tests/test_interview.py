"""Unit and integration tests for Placement Hub."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store
from app.interview import session as interview_session
from app.interview import communication, visual_coaching, skill_gap, job_matcher


def test_resume_parser_valid_and_invalid():
    with TestClient(app) as client:
        # Valid resume upload
        res_valid = client.post(
            "/api/interview/resume",
            data={
                "resume_text": "Curriculum Vitae\nExperience: Java Backend Engineer at TechCorp. Developed REST APIs, Spring Boot microservices, SQL databases. Education: B.Tech Computer Science."
            },
        )
        assert res_valid.status_code == 200
        data_valid = res_valid.json()
        assert data_valid["parsed"] is True
        assert "profile" in data_valid

        # Invalid non-resume upload (should be rejected with HTTP 400)
        res_invalid = client.post(
            "/api/interview/resume",
            data={"resume_text": "Ingredients for chocolate cake: flour, sugar, cocoa powder, eggs, milk, baking powder."},
        )
        assert res_invalid.status_code == 400
        assert "detail" in res_invalid.json()


def test_interview_session_flow():
    with TestClient(app) as client:
        # 1. Start interview
        start_res = client.post(
            "/api/interview/start",
            json={
                "learner_id": "test-candidate-1",
                "target_role": "Java Backend Developer",
                "interview_type": "Technical Round",
                "level": "Fresher",
                "duration_minutes": 15,
            },
        )
        assert start_res.status_code == 200
        start_data = start_res.json()
        session_id = start_data["session_id"]
        assert "question" in start_data

        # 2. Record camera event
        cam_res = client.post(
            "/api/interview/camera-event",
            json={"session_id": session_id, "facing_camera": True, "good_posture": True},
        )
        assert cam_res.status_code == 200

        # 3. Respond turn
        resp_res = client.post(
            "/api/interview/respond",
            json={
                "session_id": session_id,
                "user_answer": "Hello! I am a computer science graduate passionate about backend development and Spring Boot.",
                "audio_duration_seconds": 12.0,
            },
        )
        assert resp_res.status_code == 200
        resp_data = resp_res.json()
        assert "next_question" in resp_data or resp_data.get("completed") is True

        # 4. End interview & get report
        end_res = client.post(f"/api/interview/end?session_id={session_id}")
        assert end_res.status_code == 200
        end_data = end_res.json()
        assert end_data["status"] == "completed"
        assert "report" in end_data
        assert "voice_metrics" in end_data["report"]
        assert "camera_coaching" in end_data["report"]

        # 5. Apply skill gaps to roadmap
        gap_res = client.post(
            "/api/interview/apply-gaps",
            json={"learner_id": "test-candidate-1", "session_id": session_id},
        )
        assert gap_res.status_code == 200
        assert gap_res.json()["success"] is True


def test_job_matcher():
    with TestClient(app) as client:
        res = client.post(
            "/api/jobs/match",
            json={"learner_id": "test-candidate-1", "target_role": "Java Backend Developer", "location": "India"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "jobs" in data
        assert len(data["jobs"]) > 0
        first_job = data["jobs"][0]
        assert "match_percentage" in first_job
        assert first_job["match_percentage"] >= 45.0
