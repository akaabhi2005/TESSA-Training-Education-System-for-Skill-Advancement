"""Adaptive diagnostic.

Six questions, chosen by information gain rather than by syllabus order: we
ask about the skills that matter for the target role AND where our estimate is
shakiest. A self-reported "intermediate Python" that misses both decorator
questions is worth more than another paragraph of intake chat.

Question text is generated once per skill and cached to disk, so the same demo
run costs nothing the second time and the questions do not change mid-demo.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .. import llm
from ..catalog import Catalog
from ..schemas import LearnerProfile
from .profiler import probe_skills

SYSTEM = """You write single multiple-choice diagnostic questions to estimate whether
someone actually has a technical skill.

Rules:
- One question, four options, exactly one correct.
- Target the exact level stated (beginner or intermediate).
  - If level is beginner, ask about core concepts, syntax basics, and fundamental usage. Do NOT ask about advanced optimization (e.g. mixed-precision training, gradient clipping, custom kernels).
  - If level is intermediate, test real working knowledge and common patterns.
- Test understanding, not recall of API names.
- Wrong options should be plausible to someone who half-knows the topic.
- No preamble, no explanation of the answer.
"""


class QuizItem(BaseModel):
    skill_id: str = ""
    skill_name: str = ""
    question: str
    options: list[str] = Field(min_length=2, max_length=5)
    correct_index: int
    # Offline placeholders ask people to rate themselves. There is no correct
    # answer to that, so it is graded on a scale rather than right/wrong -
    # otherwise picking the top option is scored as a mistake. Set by the
    # placeholder only; never by the model.
    self_report: bool = False


def build(profile: LearnerProfile, target, weight, cat: Catalog, n: int = 6) -> list[QuizItem]:
    items: list[QuizItem] = []
    for sid in probe_skills(profile, target, weight, cat, n=n):
        skill = cat.skill_by_id[sid]
        i = cat.index[sid]
        level = "intermediate" if target[i] > 0.6 else "beginner"

        item = llm.parse(
            QuizItem,
            f"Skill: {skill.name} ({skill.domain}). Level to test: {level}.",
            SYSTEM,
            effort="low",
            lane="fast",
        )
        if item is None:
            item = _placeholder(skill.name, sid)

        item.skill_id = sid
        item.skill_name = skill.name
        items.append(item)
    return items


def _placeholder(name: str, sid: str) -> QuizItem:
    """Offline fallback. Self-report is worse than a measured answer but better
    than pretending we asked - we mark it so the UI can say so."""
    return QuizItem(
        skill_id=sid,
        skill_name=name,
        question=f"How would you rate your working knowledge of {name}?",
        options=[
            "Never used it",
            "Followed a tutorial",
            "Used it on a real task",
            "Could teach it",
        ],
        correct_index=3,
        self_report=True,
    )


def grade(items: list[QuizItem], answers: dict[str, int]) -> dict[str, float]:
    """skill_id -> score in [0,1].

    Knowledge questions get 1.0 for correct answer and 0.0 for wrong answers.
    Self-report items are graded on a scale instead.
    """
    out: dict[str, float] = {}
    for item in items:
        if item.skill_id not in answers:
            continue
        chosen = answers[item.skill_id]

        if item.self_report:
            span = max(len(item.options) - 1, 1)
            out[item.skill_id] = round(min(1.0, max(0, chosen) / span) * 0.7, 3)
            continue

        if chosen == item.correct_index:
            out[item.skill_id] = 1.0
        else:
            out[item.skill_id] = 0.0
    return out
