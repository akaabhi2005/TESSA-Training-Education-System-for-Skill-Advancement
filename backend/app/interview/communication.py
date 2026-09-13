"""Deterministic and qualitative Voice & Communication metrics analyzer."""

from __future__ import annotations

import re
from typing import Any
from .session import VoiceMetrics, InterviewTurn

FILLER_WORDS = {"umm", "um", "uh", "actually", "like", "basically", "you know", "honestly", "so yeah", "i mean"}


def analyze_communication(turns: list[InterviewTurn]) -> VoiceMetrics:
    """Calculate communication metrics from transcript turns."""
    if not turns:
        return VoiceMetrics()

    total_words = 0
    filler_count = 0
    fillers_found: list[str] = []
    total_duration_sec = 0.0
    answer_lengths: list[int] = []

    for turn in turns:
        text = turn.user_answer.strip()
        if not text:
            continue
        
        words = re.findall(r"\b\w+\b", text.lower())
        count = len(words)
        total_words += count
        answer_lengths.append(count)

        # Count filler words
        for w in words:
            if w in FILLER_WORDS:
                filler_count += 1
                if w not in fillers_found:
                    fillers_found.append(w)
        
        # Audio duration or estimate 3.5 words/sec if duration not passed
        dur = turn.audio_duration_seconds if turn.audio_duration_seconds > 0 else (count / 2.5)
        total_duration_sec += max(dur, 1.0)

    avg_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0.0
    minutes = max(total_duration_sec / 60.0, 0.1)
    pace_wpm = round(total_words / minutes, 1)

    # Clarity score formula: base 85, penalty for extreme fillers or very low/high pace
    clarity_score = 85.0
    if filler_count > 10:
        clarity_score -= min((filler_count - 10) * 1.5, 20.0)
    if pace_wpm < 80 or pace_wpm > 180:
        clarity_score -= 10.0
    if avg_length < 15:
        clarity_score -= 10.0

    clarity_score = max(min(round(clarity_score, 1), 100.0), 30.0)

    # Structure feedback
    if filler_count > 8:
        feedback = f"Try to reduce filler words such as '{', '.join(fillers_found[:3])}'. Pause silently instead."
    elif pace_wpm < 100:
        feedback = "Your speaking pace is slightly slow. Aim for a confident, steady flow around 120-150 WPM."
    elif pace_wpm > 170:
        feedback = "Your speaking pace is quite fast. Slow down slightly to ensure clear articulation."
    elif avg_length < 20:
        feedback = "Answers were a bit brief. Use the STAR technique (Situation, Task, Action, Result) for detailed responses."
    else:
        feedback = "Excellent speaking pace and clear answer structuring!"

    return VoiceMetrics(
        total_words=total_words,
        speaking_pace_wpm=pace_wpm,
        filler_words_count=filler_count,
        filler_words_found=fillers_found,
        pause_count=max(int(filler_count * 0.7), 1),
        repetition_count=max(int(filler_count * 0.4), 0),
        average_answer_length=round(avg_length, 1),
        clarity_score=clarity_score,
        structure_feedback=feedback,
    )
