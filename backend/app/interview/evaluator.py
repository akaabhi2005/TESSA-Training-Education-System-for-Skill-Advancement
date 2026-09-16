"""Gemini and structured rubric evaluation of full interview transcript based on real candidate data."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import llm
from .session import InterviewSession, InterviewEvaluationReport
from .communication import analyze_communication
from .visual_coaching import process_visual_coaching

log = logging.getLogger(__name__)


def evaluate_interview_session(session: InterviewSession) -> InterviewEvaluationReport:
    """Evaluate candidate transcript across multi-dimensional criteria using real data entered."""
    turns = session.turns
    camera_coaching = process_visual_coaching(session.camera_raw_events)

    # 1. Check if candidate submitted any answers
    valid_answers = [t for t in turns if t.user_answer and t.user_answer.strip()]
    if not turns or not valid_answers:
        voice = analyze_communication([])
        topic_names = [t.name for t in session.blueprint_topics] if session.blueprint_topics else ["Role core skills"]
        return InterviewEvaluationReport(
            overall_score=0.0,
            percentile_rank=0.0,
            star_method_score=0.0,
            category_scores={
                "Technical Knowledge": 0.0,
                "Problem Solving": 0.0,
                "DSA": 0.0,
                "CS Fundamentals": 0.0,
                "Project Knowledge": 0.0,
                "Communication": 0.0,
            },
            strong_areas=[],
            needs_improvement=["No verbal or written answers were submitted during this interview session."],
            missed_concepts=topic_names,
            actionable_suggestions=["Participate in the interview questions by typing or speaking detailed responses."],
            question_reviews=[
                {
                    "turn_index": t.turn_index,
                    "question": t.question,
                    "user_answer": "[No response recorded]",
                    "feedback": "Question was skipped without response.",
                    "ideal_model_answer": f"A comprehensive response to '{t.question[:90]}' should describe relevant technical architecture, trade-offs, and practical implementations.",
                    "turn_score": 0.0,
                }
                for t in turns
            ],
            voice_metrics=voice,
            camera_coaching=camera_coaching,
        )

    # 2. Compile real transcript with elapsed timing
    transcript_blocks = []
    for idx, turn in enumerate(turns, 1):
        ans = turn.user_answer.strip()
        dur = f" ({turn.audio_duration_seconds:.1f}s)" if turn.audio_duration_seconds > 0 else ""
        transcript_blocks.append(f"Turn {idx} Question: {turn.question}\nTurn {idx} Candidate Answer{dur}: {ans or '[No response]'}")
    full_transcript = "\n\n".join(transcript_blocks)

    voice_metrics = analyze_communication(turns)

    # Context about topics and company pack
    topics_str = ", ".join(f"{t.name} (concepts: {', '.join(t.key_concepts[:4])})" for t in session.blueprint_topics) if session.blueprint_topics else "Standard role syllabus"
    company_context = f"Target Company Pack: {session.company_pack}\n" if session.company_pack else ""
    resume_context = f"Candidate Resume Highlights: {', '.join(session.resume_summary.get('skills', [])[:6])}\n" if session.resume_summary and session.resume_summary.get("skills") else ""

    prompt = (
        f"You are a Senior Principal Technical Interviewer evaluating a candidate's REAL mock interview.\n"
        f"Role: {session.target_role} ({session.level} level) | Round: {session.interview_type}\n"
        f"{company_context}{resume_context}"
        f"Syllabus Topics Covered: {topics_str}\n\n"
        f"ACTUAL CANDIDATE TRANSCRIPT ({len(turns)} questions answered):\n"
        f"{full_transcript[:6500]}\n\n"
        "STRICT EVALUATION INSTRUCTIONS:\n"
        "1. Base ALL scores and assessments STRICTLY on what the candidate actually wrote or spoke.\n"
        "2. If an answer was vague, brief (<15 words), or generic, score that turn between 10 and 40.\n"
        "3. If an answer was clear, used proper technical terminology, and addressed the question directly, score that turn between 65 and 95.\n"
        "4. For EACH question in 'question_reviews':\n"
        "   - 'turn_score': integer (0 to 100) reflecting technical correctness of their actual answer.\n"
        "   - 'feedback': 1-2 sentences of specific critique pointing out what they got right and what specific concepts were missing in their answer.\n"
        "   - 'ideal_model_answer': 2-3 sentences of a stellar, technically accurate model response to THAT specific question.\n"
        "5. 'strong_areas': list 2-4 specific technical concepts the candidate actually proved competence in from their transcript.\n"
        "6. 'needs_improvement': list 2-4 specific technical skills/topics where the candidate was weak, incomplete, or incorrect.\n"
        "7. 'missed_concepts': list 2-4 technical terms, edge cases, complexity details, or design patterns omitted in their responses.\n"
        "8. 'actionable_suggestions': list 2-3 practical, concrete study recommendations for the candidate.\n"
        "9. Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "technical_knowledge": 70,\n'
        '  "problem_solving": 65,\n'
        '  "dsa": 60,\n'
        '  "cs_fundamentals": 70,\n'
        '  "project_knowledge": 75,\n'
        '  "system_design": 65,\n'
        '  "strong_areas": ["..."],\n'
        '  "needs_improvement": ["..."],\n'
        '  "missed_concepts": ["..."],\n'
        '  "actionable_suggestions": ["..."],\n'
        '  "question_reviews": [\n'
        '    {\n'
        '      "turn_index": 1,\n'
        '      "turn_score": 75,\n'
        '      "feedback": "Good explanation of...",\n'
        '      "ideal_model_answer": "An ideal answer should explain..."\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        raw_res = llm.text(prompt, system="You are an expert Technical Interview Evaluator. Always output pure valid JSON.") or ""
        start = raw_res.find("{")
        end = raw_res.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(raw_res[start : end + 1])
            
            cat_scores = {
                "Technical Knowledge": float(data.get("technical_knowledge", 65)),
                "Problem Solving": float(data.get("problem_solving", 60)),
                "DSA": float(data.get("dsa", 60)),
                "CS Fundamentals": float(data.get("cs_fundamentals", 65)),
                "Project Knowledge": float(data.get("project_knowledge", 70)),
                "Communication": voice_metrics.clarity_score,
            }
            if session.interview_type == "System Design" or "system_design" in data:
                cat_scores["System Design"] = float(data.get("system_design", 60))

            overall = round(sum(cat_scores.values()) / len(cat_scores), 1)
            percentile = min(round(overall * 1.06 + 3.0, 1), 99.0) if overall > 20 else round(overall * 0.8, 1)
            star_score = round(min(overall * 0.9 + (voice_metrics.clarity_score * 0.1), 100.0), 1)

            raw_q_reviews = {qr.get("turn_index"): qr for qr in data.get("question_reviews", [])}

            # Map reviews for every real turn
            q_reviews = []
            for t in turns:
                ans = t.user_answer.strip()
                ans_words = len(ans.split())
                review = raw_q_reviews.get(t.turn_index, {})

                # Validate turn score
                t_score = review.get("turn_score")
                if t_score is None:
                    t_score = min(max(ans_words * 2, 25), 85) if ans_words > 0 else 0
                t_score = round(float(t_score), 1)

                feedback = review.get("feedback")
                if not feedback:
                    if ans_words < 10:
                        feedback = "Answer was too brief. Elaborate on implementation details and practical trade-offs."
                    else:
                        feedback = "Addressed the core question; focus on including specific complexity and architecture details."

                ideal = review.get("ideal_model_answer")
                if not ideal:
                    ideal = f"An ideal response to '{t.question[:80]}' should explain core components, trade-offs, and cite production use cases using STAR structure."

                q_reviews.append({
                    "turn_index": t.turn_index,
                    "question": t.question,
                    "user_answer": ans or "[No response recorded]",
                    "feedback": feedback,
                    "ideal_model_answer": ideal,
                    "turn_score": t_score,
                })

            strong = data.get("strong_areas") or []
            weak = data.get("needs_improvement") or []
            missed = data.get("missed_concepts") or []
            sugg = data.get("actionable_suggestions") or []

            if not strong:
                strong = [t.name for t in session.blueprint_topics[:2]] if session.blueprint_topics else ["Basic Syntax & Communication"]
            if not weak:
                weak = [t.name for t in session.blueprint_topics[2:4]] if len(session.blueprint_topics) > 2 else ["Algorithmic Optimization", "Edge Case Handling"]

            return InterviewEvaluationReport(
                overall_score=overall,
                percentile_rank=percentile,
                star_method_score=star_score,
                category_scores=cat_scores,
                strong_areas=strong,
                needs_improvement=weak,
                missed_concepts=missed,
                actionable_suggestions=sugg,
                question_reviews=q_reviews,
                voice_metrics=voice_metrics,
                camera_coaching=camera_coaching,
            )
    except Exception as exc:
        log.warning("Gemini evaluation error, using content-aware heuristic: %s", exc)

    # 3. Content-aware heuristic evaluation derived from actual transcript text
    return _evaluate_transcript_heuristically(session, turns, voice_metrics, camera_coaching)


def _evaluate_transcript_heuristically(
    session: InterviewSession,
    turns: list[Any],
    voice_metrics: Any,
    camera_coaching: Any,
) -> InterviewEvaluationReport:
    """Intelligent, content-aware evaluation derived from candidate's actual answers when LLM is unavailable."""
    all_answers_text = " ".join(t.user_answer.lower() for t in turns)
    all_words = re.findall(r"\b\w+\b", all_answers_text)
    total_words = len(all_words)
    avg_words = total_words / max(len(turns), 1)

    tech_keywords = {
        "architecture", "algorithm", "complexity", "time", "space", "database", "sql", "index",
        "api", "rest", "http", "class", "interface", "method", "thread", "async", "cache",
        "latency", "scaling", "microservices", "docker", "testing", "git", "exception",
        "memory", "pointer", "hash", "tree", "graph", "dynamic", "sorting", "search",
        "spring", "react", "python", "java", "node", "aws", "cloud", "security", "acid"
    }
    keywords_found = set(w for w in all_words if w in tech_keywords)

    q_reviews = []
    turn_scores = []
    detected_weak_topics = []
    detected_strong_topics = []

    for idx, t in enumerate(turns):
        ans = t.user_answer.strip()
        words = re.findall(r"\b\w+\b", ans.lower())
        word_count = len(words)
        
        topic = session.blueprint_topics[min(idx, len(session.blueprint_topics) - 1)] if session.blueprint_topics else None
        topic_concepts = [c.lower() for c in (topic.key_concepts if topic else [])]
        matched_concepts = [c for c in topic_concepts if c in ans.lower()]

        if word_count == 0:
            score = 0.0
            feedback = "No response was recorded for this question."
        elif word_count < 10 or any(phrase in ans.lower() for phrase in ["dont know", "don't know", "idk", "no idea", "not sure", "skip"]):
            score = 25.0
            feedback = "Answer was insufficient. Candidate showed uncertainty on core topic concepts."
            if topic:
                detected_weak_topics.append(topic.name)
        elif word_count < 25:
            score = 50.0 + (len(matched_concepts) * 8)
            feedback = "Basic answer provided. Expand on the underlying mechanics and edge case considerations."
            if topic and not matched_concepts:
                detected_weak_topics.append(topic.name)
        else:
            score = min(65.0 + (len(matched_concepts) * 8) + (min(word_count, 80) * 0.2), 94.0)
            feedback = "Good detailed response with appropriate technical depth and practical context."
            if topic and (matched_concepts or score >= 75):
                detected_strong_topics.append(topic.name)

        score = round(score, 1)
        turn_scores.append(score)

        topic_name = topic.name if topic else "Technical Problem Solving"
        key_refs = ", ".join(topic.key_concepts[:3]) if topic and topic.key_concepts else "scalability, trade-offs, and edge cases"
        ideal = f"An ideal answer for '{t.question[:70]}' should clearly address {topic_name}, specifically explaining {key_refs} with concrete architectural examples."

        q_reviews.append({
            "turn_index": t.turn_index,
            "question": t.question,
            "user_answer": ans or "[No response recorded]",
            "feedback": feedback,
            "ideal_model_answer": ideal,
            "turn_score": score,
        })

    avg_turn_score = sum(turn_scores) / max(len(turn_scores), 1)
    
    cat_scores = {
        "Technical Knowledge": round(min(max(avg_turn_score * 0.95 + len(keywords_found) * 1.5, 20.0), 96.0), 1),
        "Problem Solving": round(min(max(avg_turn_score * 0.9 + (15 if avg_words > 30 else 0), 20.0), 92.0), 1),
        "DSA": round(min(max(avg_turn_score * 0.85, 20.0), 90.0), 1),
        "CS Fundamentals": round(min(max(avg_turn_score * 0.92, 20.0), 94.0), 1),
        "Project Knowledge": round(min(max(avg_turn_score * 0.98 + (10 if "project" in all_answers_text else 0), 20.0), 95.0), 1),
        "Communication": voice_metrics.clarity_score,
    }
    if session.interview_type == "System Design":
        cat_scores["System Design"] = round(min(max(avg_turn_score * 0.9 + ("microservices" in all_answers_text) * 10, 20.0), 95.0), 1)

    overall = round(sum(cat_scores.values()) / len(cat_scores), 1)
    percentile = min(round(overall * 1.06 + 3.0, 1), 99.0) if overall > 20 else round(overall * 0.8, 1)
    star_score = round(min(overall * 0.9 + (voice_metrics.clarity_score * 0.1), 100.0), 1)

    strong = list(dict.fromkeys(detected_strong_topics))
    if not strong:
        strong = [k.title() for k in list(keywords_found)[:3]] or ["Basic Problem Approach"]

    weak = list(dict.fromkeys(detected_weak_topics))
    if not weak and session.blueprint_topics:
        weak = [t.name for t in session.blueprint_topics if t.name not in strong][:3]
    if not weak:
        weak = ["Complex Edge Case Handling", "Time & Space Optimization"]

    missed = []
    for t in session.blueprint_topics:
        if t.name in weak:
            missed.extend(t.key_concepts[:2])
    if not missed:
        missed = ["Algorithmic Complexity Trade-offs", "Production Error Handling"]
    missed = list(dict.fromkeys(missed))[:4]

    sugg = [f"Deep dive into {topic} fundamentals with hands-on practice problems." for topic in weak[:2]]
    sugg.append("Structure answers using STAR (Situation, Task, Action, Result) to clearly articulate technical impact.")

    return InterviewEvaluationReport(
        overall_score=overall,
        percentile_rank=percentile,
        star_method_score=star_score,
        category_scores=cat_scores,
        strong_areas=strong,
        needs_improvement=weak,
        missed_concepts=missed,
        actionable_suggestions=sugg,
        question_reviews=q_reviews,
        voice_metrics=voice_metrics,
        camera_coaching=camera_coaching,
    )

