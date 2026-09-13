"""Resume PDF text extraction and strict Gemini AI resume verification & parsing."""

from __future__ import annotations

import io
import json
import logging
from typing import Any

from .. import llm

log = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF file bytes using pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text_parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(text_parts).strip()
    except Exception as exc:
        log.warning("PDF extraction failed: %s", exc)
        return ""


def validate_and_parse_resume(text: str) -> tuple[bool, str, dict[str, Any]]:
    """Validate if uploaded text is a genuine resume/CV using Gemini AI, and parse structured details."""
    clean_text = text.strip()
    if not clean_text or len(clean_text) < 30:
        return False, "Uploaded file is empty or too short to be a valid resume.", {}

    prompt = (
        "Analyze the following document text carefully as a strict AI Technical Recruiter.\n"
        "Determine if this document is a genuine Candidate Resume / Curriculum Vitae (CV) containing work experience, education, skills, projects, or professional background.\n"
        "If the document is a random article, homework assignment, invoice, code snippet, news article, syllabus, or non-resume file, set 'is_valid_resume' to false.\n\n"
        "Return ONLY a JSON object matching this schema:\n"
        "{\n"
        '  "is_valid_resume": true,\n'
        '  "rejection_reason": "Clear explanation if not a resume, otherwise empty string",\n'
        '  "skills": ["java", "spring boot", "sql", ...],\n'
        '  "projects": [{"title": "...", "tech_stack": [...], "description": "..."}],\n'
        '  "experience": [{"role": "...", "company": "...", "duration": "..."}],\n'
        '  "education": [{"degree": "...", "institution": "..."}],\n'
        '  "technologies": ["git", "docker", "aws", ...],\n'
        '  "summary": "Short 2-line summary of candidate background"\n'
        "}\n\n"
        f"DOCUMENT TEXT:\n{clean_text[:4000]}"
    )

    try:
        raw_response = llm.text(prompt, system="You are a strict technical recruiter and resume verification classifier.") or ""
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(raw_response[start : end + 1])
            is_valid = bool(data.get("is_valid_resume", True))
            reason = data.get("rejection_reason") or "Uploaded document is not a valid resume/CV."
            if not is_valid:
                return False, reason, {}
            return True, "", {
                "skills": data.get("skills") or [],
                "projects": data.get("projects") or [],
                "experience": data.get("experience") or [],
                "education": data.get("education") or [],
                "technologies": data.get("technologies") or [],
                "summary": data.get("summary") or "Candidate profile extracted from resume.",
            }
    except Exception as exc:
        log.warning("Gemini resume validation error: %s", exc)

    # Heuristic fallback check if Gemini is offline/unreachable
    words = [w.strip(".,;:()[]{}").lower() for w in clean_text.split()]
    resume_keywords = {
        "resume", "curriculum", "vitae", "cv", "education", "experience",
        "skills", "projects", "b.tech", "btech", "m.tech", "mtech", "b.e",
        "degree", "university", "college", "engineer", "developer", "internship",
        "employment", "work history", "objective", "certifications", "technologies"
    }
    match_count = len(set(words).intersection(resume_keywords))
    if match_count < 2:
        return False, "Uploaded file does not appear to be a valid Resume/CV. Please upload a file containing professional background, education, or skills.", {}

    found_skills = list(set(words).intersection({"python", "java", "c++", "javascript", "react", "spring", "sql", "git", "docker", "aws", "dsa", "node"}))
    return True, "", {
        "skills": found_skills,
        "projects": [],
        "experience": [],
        "education": [],
        "technologies": found_skills,
        "summary": "Candidate profile extracted from text.",
    }


def parse_resume_to_structured_profile(text: str) -> dict[str, Any]:
    """Legacy helper maintained for compatibility."""
    valid, _, profile = validate_and_parse_resume(text)
    return profile if valid else {
        "skills": [],
        "projects": [],
        "experience": [],
        "education": [],
        "technologies": [],
        "summary": "Invalid or unparsed resume.",
    }
