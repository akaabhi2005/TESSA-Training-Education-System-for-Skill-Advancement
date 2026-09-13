"""Gemini-powered adaptive interviewer for generating realistic interview intro and follow-ups."""

from __future__ import annotations

import json
import logging
from typing import Any

from .. import llm
from .blueprint import BlueprintTopic
from .session import InterviewTurn

log = logging.getLogger(__name__)


def generate_initial_question(
    target_role: str,
    interview_type: str,
    level: str,
    topics: list[BlueprintTopic],
    resume_summary: dict[str, Any] | None = None,
) -> str:
    """Generate a realistic opening interviewer greeting, role context, and candidate self-introduction request."""
    resume_context = ""
    if resume_summary and resume_summary.get("skills"):
        skills_str = ", ".join(resume_summary.get("skills", [])[:5])
        resume_context = f"The candidate's resume highlights skills in: {skills_str}."

    prompt = (
        f"You are an expert AI Interviewer conducting a realistic {level}-level mock interview for a '{target_role}' position ({interview_type}).\n"
        f"{resume_context}\n\n"
        "INSTRUCTIONS FOR TURN 1:\n"
        "1. Start with a warm, professional interviewer greeting.\n"
        f"2. Welcome the candidate to the {interview_type} for the {target_role} position.\n"
        "3. Ask the candidate to introduce themselves, give a brief overview of their technical background, and share what excites them about this role.\n"
        "4. Keep it concise, engaging, and clear like a real corporate interviewer.\n"
        "5. DO NOT ask hard technical/coding questions on Turn 1; save technical deep dives for Turn 2 after candidate introduces themselves.\n"
        "Return ONLY the spoken interviewer text."
    )

    try:
        greeting = (llm.text(prompt, system="You are a realistic corporate AI Interviewer.") or "").strip()
        if greeting and len(greeting) > 15:
            return greeting.strip('"')
    except Exception as exc:
        log.warning("Gemini initial greeting generation error: %s", exc)

    return (
        f"Hello! Welcome to your {interview_type} for the {target_role} role. I'm your AI interviewer today. "
        f"To get started, could you please introduce yourself, give a quick overview of your background, and tell me what interests you about this role?"
    )


def generate_next_adaptive_question(
    target_role: str,
    interview_type: str,
    level: str,
    topics: list[BlueprintTopic],
    turns: list[InterviewTurn],
    resume_summary: dict[str, Any] | None = None,
) -> str:
    """Generate an adaptive follow-up or next technical/HR round question based on transcript history."""
    if not turns:
        return generate_initial_question(target_role, interview_type, level, topics, resume_summary)

    last_turn = turns[-1]
    turn_count = len(turns)
    current_topic_idx = min((turn_count - 1) // 2, len(topics) - 1)
    current_topic = topics[current_topic_idx].name if topics else "Core Technical Skills"
    key_concepts = ", ".join(topics[current_topic_idx].key_concepts) if topics and topics[current_topic_idx].key_concepts else "Core principles"

    # Format transcript history
    history_lines = []
    for t in turns[-4:]:
        history_lines.append(f"Interviewer: {t.question}")
        history_lines.append(f"Candidate: {t.user_answer}")
    history_str = "\n".join(history_lines)

    if turn_count == 1:
        # Candidate just introduced themselves in Turn 1 -> Transition to Topic 1
        prompt = (
            f"You are an expert AI Technical Interviewer conducting a realistic {level}-level mock interview for '{target_role}' ({interview_type}).\n"
            f"Candidate just introduced themselves: \"{last_turn.user_answer}\"\n\n"
            f"First Topic Focus: {current_topic} ({key_concepts})\n\n"
            "INSTRUCTIONS:\n"
            "1. Briefly acknowledge their introduction in 1 warm sentence.\n"
            f"2. Seamlessly transition into the first key technical/HR question on '{current_topic}'.\n"
            "3. Ask EXACTLY ONE clear, professional question. Return ONLY the interviewer speech."
        )
    else:
        # Turn 2+ adaptive probing or topic transition
        prompt = (
            f"You are an expert AI Technical Interviewer conducting a realistic {level}-level mock interview for '{target_role}' ({interview_type}).\n"
            f"Current Topic Focus: {current_topic} ({key_concepts})\n\n"
            f"RECENT CONVERSATION TRANSCRIPT:\n{history_str}\n\n"
            "INSTRUCTIONS:\n"
            "1. Evaluate candidate's previous response in context.\n"
            "2. If their answer was partial or mentioned a key technique, ask a probing follow-up question.\n"
            "3. If their answer was comprehensive, move naturally to the next blueprint aspect or scenario.\n"
            "4. Ask EXACTLY ONE question. DO NOT reveal marks or feedback during the interview. Return ONLY the question text."
        )

    try:
        question = (llm.text(prompt, system="You are an expert AI Technical Interviewer.") or "").strip()
        if question and len(question) > 10:
            return question.strip('"')
    except Exception as exc:
        log.warning("Gemini adaptive follow-up generation error: %s", exc)

    return f"Thanks for explaining. Building on that, how would you approach solving edge cases and design decisions when working with {current_topic}?"
