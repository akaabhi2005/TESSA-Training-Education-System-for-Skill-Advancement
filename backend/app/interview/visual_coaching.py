"""Camera & Visual Coaching processor.

CRITICAL RULE:
Camera analysis (eye contact, head movements, posture) is used EXCLUSIVELY for
coaching feedback (e.g. eye contact tips). It is strictly non-evaluative and MUST NEVER
be used for technical scores, job suitability, or job-match percentages.
"""

from __future__ import annotations

from typing import Any
from .session import CameraCoachingMetrics


def process_visual_coaching(raw_events: list[dict[str, Any]]) -> CameraCoachingMetrics:
    """Aggregate browser-side MediaPipe coaching signals."""
    if not raw_events:
        return CameraCoachingMetrics(
            camera_enabled=False,
            facing_camera_percentage=0.0,
            looking_away_count=0,
            excessive_head_movement_count=0,
            posture_consistency_percentage=0.0,
            coaching_tips=[
                "Camera was not enabled during this session.",
                "Enable your camera to receive real-time eye contact, posture, and non-verbal coaching feedback."
            ]
        )

    facing_samples = [e.get("facing_camera", True) for e in raw_events]
    posture_samples = [e.get("good_posture", True) for e in raw_events]
    looking_away = sum(1 for e in raw_events if not e.get("facing_camera", True))
    head_movements = sum(1 for e in raw_events if e.get("excessive_head_movement", False))

    facing_pct = round((sum(facing_samples) / max(len(facing_samples), 1)) * 100, 1)
    posture_pct = round((sum(posture_samples) / max(len(posture_samples), 1)) * 100, 1)

    tips = []
    if facing_pct < 75.0:
        tips.append("Try to look directly into the camera lens more consistently to build strong rapport.")
    else:
        tips.append("Great camera facing consistency throughout the mock session.")

    if looking_away > 5:
        tips.append("Frequent looking away detected. Glance at notes sparingly during responses.")

    if head_movements > 4:
        tips.append("Noticeable head movement detected. Keep your posture steady when delivering answers.")

    if posture_pct < 80.0:
        tips.append("Adjust your seating setup to maintain an upright, open posture.")

    return CameraCoachingMetrics(
        facing_camera_percentage=facing_pct,
        looking_away_count=looking_away,
        excessive_head_movement_count=head_movements,
        posture_consistency_percentage=posture_pct,
        coaching_tips=tips,
    )
