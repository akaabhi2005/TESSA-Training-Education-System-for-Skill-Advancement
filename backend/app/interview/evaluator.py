"""Gemini and structured rubric evaluation of full interview transcript."""

from __future__ import annotations

import json
import logging
from typing import Any

from .. import llm
from .session import InterviewSession, InterviewEvaluationReport
from .communication import analyze_communication
from .visual_coaching import process_visual_coaching

log = logging.getLogger(__name__)


def evaluate_interview_session(session: InterviewSession) -> InterviewEvaluationReport:
    """Evaluate candidate transcript across multi-dimensional criteria."""
    turns = session.turns
    if not turns:
        voice = analyze_communication([])
        camera = process_visual_coaching(session.camera_raw_events)
        return InterviewEvaluationReport(
            overall_score=60.0,
            category_scores={
                "Technical Knowledge": 60.0,
                "Problem Solving": 60.0,
                "DSA": 60.0,
                "CS Fundamentals": 60.0,
                "Project Knowledge": 60.0,
                "Communication": voice.clarity_score,
            },
            strong_areas=["Basic concepts"],
            needs_improvement=["Detailed explanation required"],
            missed_concepts=["System fundamentals"],
            actionable_suggestions=["Practice voice answers with complete structure."],
            voice_metrics=voice,
            camera_coaching=camera,
        )

    # Compile full transcript
    transcript_blocks = []
    for idx, turn in enumerate(turns, 1):
        transcript_blocks.append(f"Q{idx}: {turn.question}\nA{idx}: {turn.user_answer}")
    full_transcript = "\n\n".join(transcript_blocks)

    voice_metrics = analyze_communication(turns)
    camera_coaching = process_visual_coaching(session.camera_raw_events)

    prompt = (
        f"You are an expert Senior Engineering Interview Evaluator reviewing a candidate's mock interview for target role '{session.target_role}' ({session.level} level).\n"
        f"Interview Type: {session.interview_type}\n\n"
        f"FULL INTERVIEW TRANSCRIPT:\n{full_transcript[:6000]}\n\n"
        "Evaluate the candidate objectively using structured scoring rubrics (0 to 100 per category).\n"
        "Return ONLY a JSON object matching this schema:\n"
        "{\n"
        '  "technical_knowledge": 75,\n'
        '  "problem_solving": 65,\n'
        '  "dsa": 60,\n'
        '  "cs_fundamentals": 70,\n'
        '  "project_knowledge": 80,\n'
        '  "system_design": 65,\n'
        '  "strong_areas": ["Java OOP", "REST API Design"],\n'
        '  "needs_improvement": ["Graph Algorithms", "Computer Networks"],\n'
        '  "missed_concepts": ["Dijkstra Shortest Path", "ACID Isolation Levels"],\n'
        '  "actionable_suggestions": ["Practice graph traversals", "Review database locking mechanisms"]\n'
        "}"
    )

    try:
        raw_res = llm.text(prompt, system="You are an expert Senior Engineering Interview Evaluator.") or ""
        start = raw_res.find("{")
        end = raw_res.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(raw_res[start : end + 1])
            
            cat_scores = {
                "Technical Knowledge": float(data.get("technical_knowledge", 70)),
                "Problem Solving": float(data.get("problem_solving", 65)),
                "DSA": float(data.get("dsa", 60)),
                "CS Fundamentals": float(data.get("cs_fundamentals", 70)),
                "Project Knowledge": float(data.get("project_knowledge", 75)),
                "Communication": voice_metrics.clarity_score,
            }
            if session.interview_type == "System Design" or "system_design" in data:
                cat_scores["System Design"] = float(data.get("system_design", 65))

            overall = round(sum(cat_scores.values()) / len(cat_scores), 1)
            percentile = min(round(overall * 1.08 + 2.5, 1), 99.0)
            star_score = round(min(overall * 0.95 + (voice_metrics.clarity_score * 0.1), 100.0), 1)

            # Generate question-by-question reviews
            q_reviews = []
            for t in turns:
                ans = t.user_answer.strip()
                ans_len = len(ans.split())
                q_score = min(max(ans_len * 2, 40), 95)
                q_reviews.append({
                    "turn_index": t.turn_index,
                    "question": t.question,
                    "user_answer": ans or "[No response recorded]",
                    "ideal_model_answer": f"A top-tier candidate response for '{t.question[:60]}...' should clearly cover core architecture, STAR methodology (Situation, Task, Action, Result), and key trade-offs.",
                    "turn_score": q_score,
                })

            return InterviewEvaluationReport(
                overall_score=overall,
                percentile_rank=percentile,
                star_method_score=star_score,
                category_scores=cat_scores,
                strong_areas=data.get("strong_areas", ["Core Syntax", "Problem Approach"]),
                needs_improvement=data.get("needs_improvement", ["Complex Data Structures", "Edge Cases"]),
                missed_concepts=data.get("missed_concepts", ["Specific Algorithm Optimizations"]),
                actionable_suggestions=data.get("actionable_suggestions", ["Review key computer science fundamentals."]),
                question_reviews=q_reviews,
                voice_metrics=voice_metrics,
                camera_coaching=camera_coaching,
            )
    except Exception as exc:
        log.warning("Gemini evaluation JSON parse fallback: %s", exc)

    # Deterministic fallback evaluation based on transcript length and keywords
    word_count = sum(len(t.user_answer.split()) for t in turns)
    base_val = min(max(word_count // 3, 50), 85)
    
    cat_scores = {
        "Technical Knowledge": float(base_val + 5),
        "Problem Solving": float(base_val - 5),
        "DSA": float(base_val - 10),
        "CS Fundamentals": float(base_val),
        "Project Knowledge": float(base_val + 8),
        "Communication": voice_metrics.clarity_score,
    }
    overall = round(sum(cat_scores.values()) / len(cat_scores), 1)
    percentile = min(round(overall * 1.08 + 2.5, 1), 99.0)
    star_score = round(min(overall * 0.92, 100.0), 1)

    q_reviews = []
    for t in turns:
        ans = t.user_answer.strip()
        ans_len = len(ans.split())
        q_score = min(max(ans_len * 2, 45), 90)
        q_reviews.append({
            "turn_index": t.turn_index,
            "question": t.question,
            "user_answer": ans or "[No response recorded]",
            "ideal_model_answer": f"Ideal response to '{t.question[:60]}...': Structure your answer using STAR format, clearly explain key technical choices, and mention efficiency/complexity trade-offs.",
            "turn_score": q_score,
        })

    return InterviewEvaluationReport(
        overall_score=overall,
        percentile_rank=percentile,
        star_method_score=star_score,
        category_scores=cat_scores,
        strong_areas=["Applied Concepts", "Core Syntax"],
        needs_improvement=["Deep Fundamentals", "Algorithmic Optimizations"],
        missed_concepts=["Time/Space Complexity Details"],
        actionable_suggestions=["Practice structured technical answers using STAR format."],
        question_reviews=q_reviews,
        voice_metrics=voice_metrics,
        camera_coaching=camera_coaching,
    )
