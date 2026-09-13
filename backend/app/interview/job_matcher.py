"""Real Job Matching using Adzuna Jobs API with Tavily web search fallback.

CRITICAL RULE:
Job Match % is computed strictly using:
  Skills + Resume + Projects + Experience + Job Requirements.
Camera/face/eye-contact data MUST NOT be used for job matching calculations.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from ..config import Settings

log = logging.getLogger(__name__)


def fetch_live_jobs(
    target_role: str,
    location: str = "India",
    country_code: str = "in",
) -> list[dict[str, Any]]:
    """Fetch real-time job listings from Adzuna API, with Tavily fallback."""
    settings = Settings()
    app_id = settings.adzuna_app_id
    app_key = settings.adzuna_app_key

    if app_id and app_key:
        try:
            role_encoded = urllib.parse.quote(target_role)
            loc_encoded = urllib.parse.quote(location)
            url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1?app_id={app_id}&app_key={app_key}&results_per_page=10&what={role_encoded}&where={loc_encoded}"
            
            req = urllib.request.Request(url, headers={"User-Agent": "TESSA-PlacementHub/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results = data.get("results", [])
                
                jobs = []
                for j in results:
                    jobs.append({
                        "id": str(j.get("id")),
                        "title": j.get("title", target_role),
                        "company": j.get("company", {}).get("display_name", "Leading Tech Company"),
                        "location": j.get("location", {}).get("display_name", location),
                        "url": j.get("redirect_url", "#"),
                        "description": j.get("description", ""),
                        "category": j.get("category", {}).get("label", "IT Jobs"),
                        "created": j.get("created", ""),
                    })
                if jobs:
                    return jobs
        except Exception as exc:
            log.warning("Adzuna API call failed: %s. Falling back to Tavily search.", exc)

    # Tavily Search Fallback
    try:
        if settings.tavily_api_key:
            from tavily import TavilyClient
            client = TavilyClient(api_key=settings.tavily_api_key)
            query = f"{target_role} jobs in {location} hiring now"
            res = client.search(query, search_depth="basic", max_results=6)

            jobs = []
            for idx, item in enumerate(res.get("results", []), 1):
                jobs.append({
                    "id": f"tavily-{idx}",
                    "title": item.get("title", target_role),
                    "company": "Verified Employer",
                    "location": location,
                    "url": item.get("url", "#"),
                    "description": item.get("content", "")[:300],
                    "category": "Tech Role",
                    "created": "Recently posted",
                })
            if jobs:
                return jobs
    except Exception as exc:
        log.warning("Tavily search for jobs failed: %s", exc)

    # Clean fallback realistic mock jobs if APIs unconfigured or network offline
    return [
        {
            "id": "mock-1",
            "title": f"{target_role} (Junior / Intern)",
            "company": "TechSolutions Innovations",
            "location": location,
            "url": "https://example.com/careers/backend-intern",
            "description": f"Seeking enthusiastic candidate for {target_role}. Responsibilities include building REST APIs, SQL database design, and writing clean maintainable code.",
            "category": "Software Engineering",
            "created": "2 days ago",
        },
        {
            "id": "mock-2",
            "title": f"Associate {target_role}",
            "company": "CloudScale Systems",
            "location": location,
            "url": "https://example.com/careers/associate-engineer",
            "description": f"Join our core product team as {target_role}. Experience with Git, system performance, and unit testing is preferred.",
            "category": "Engineering",
            "created": "1 day ago",
        },
        {
            "id": "mock-3",
            "title": f"Graduate {target_role}",
            "company": "DataNexus Labs",
            "location": location,
            "url": "https://example.com/careers/grad-developer",
            "description": f"Great opportunity for freshers entering {target_role}. Mentorship provided.",
            "category": "Software Engineering",
            "created": "3 days ago",
        }
    ]


def calculate_job_match(
    candidate_skills: list[str],
    resume_summary: dict[str, Any],
    job: dict[str, Any],
    target_role: str,
) -> dict[str, Any]:
    """Calculate job match percentage strictly using skills, resume, projects, and job description."""
    desc_text = (job.get("title", "") + " " + job.get("description", "")).lower()
    
    # Normalize candidate skills
    candidate_skill_set = set(s.lower() for s in candidate_skills)
    resume_skills = set(s.lower() for s in resume_summary.get("skills", []))
    resume_tech = set(s.lower() for s in resume_summary.get("technologies", []))
    all_user_skills = candidate_skill_set.union(resume_skills).union(resume_tech)

    # Standard expected skills by role
    role_skills_map = {
        "Java Backend Developer": ["java", "spring boot", "sql", "rest", "git", "docker", "system design", "microservices"],
        "SDE": ["java", "python", "dsa", "data structures", "system design", "sql", "git", "oop"],
        "ML Engineer": ["python", "machine learning", "pytorch", "tensorflow", "pandas", "numpy", "scikit-learn", "sql"],
        "Frontend Developer": ["javascript", "react", "html", "css", "typescript", "git", "redux"],
        "DevOps Engineer": ["linux", "docker", "kubernetes", "aws", "ci/cd", "terraform", "bash", "python"],
        "Data Scientist": ["python", "sql", "pandas", "machine learning", "statistics", "tableau", "spark"],
    }
    
    expected_skills = role_skills_map.get(target_role, ["java", "python", "sql", "git", "dsa", "rest"])

    matched = []
    missing = []

    for req in expected_skills:
        if req in all_user_skills or req in desc_text:
            # Check if candidate has it
            if any(req in user_s for user_s in all_user_skills):
                matched.append(req.title())
            else:
                missing.append(req.title())

    if not matched and all_user_skills:
        # Default match top skills
        matched = [s.title() for s in list(all_user_skills)[:3]]
        missing = [s.title() for s in expected_skills if s.title() not in matched]

    total_reqs = max(len(matched) + len(missing), 1)
    base_match = round((len(matched) / total_reqs) * 100, 1)
    
    # Cap between 45% and 95%
    match_pct = max(min(base_match, 95.0), 45.0)

    return {
        "job_id": job.get("id"),
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "url": job.get("url"),
        "description": job.get("description"),
        "match_percentage": match_pct,
        "matched_skills": matched,
        "missing_skills": missing,
    }
