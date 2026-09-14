"""Interview blueprint definitions for Placement Hub roles and topics."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

InterviewType = Literal["Technical Round", "HR & Behavioral Round", "Full Mock Interview (All Rounds)", "Technical", "HR", "Full Mock Interview"]
ExperienceLevel = Literal["Internship", "Fresher", "Intermediate", "Expert"]
DurationMinutes = Literal[15, 30, 45, 60]


class InterviewSetupRequest(BaseModel):
    learner_id: str
    target_role: str = "Java Backend Developer"
    interview_type: str = "Technical Round"
    level: str = "Fresher"
    duration_minutes: int = 30
    resume_text: str | None = None
    resume_filename: str | None = None


class BlueprintTopic(BaseModel):
    name: str
    weight: float = 1.0
    key_concepts: list[str] = Field(default_factory=list)


ROLE_BLUEPRINTS: dict[str, dict[str, list[BlueprintTopic]]] = {
    "Java Backend Developer": {
        "Technical Round": [
            BlueprintTopic(name="Java OOP & Core Syntax", weight=1.5, key_concepts=["Inheritance", "Polymorphism", "Abstraction", "Collections Framework", "Generics"]),
            BlueprintTopic(name="Spring Boot Framework", weight=1.5, key_concepts=["Dependency Injection", "REST Controllers", "Spring Data JPA", "Spring Security"]),
            BlueprintTopic(name="Database & SQL", weight=1.2, key_concepts=["Indexing", "Transactions", "ACID", "Joins", "ORM Mapping"]),
            BlueprintTopic(name="Concurrency & Multithreading", weight=1.0, key_concepts=["ExecutorService", "Synchronization", "Volatile", "Locks"]),
        ],
        "HR & Behavioral Round": [
            BlueprintTopic(name="Background & Motivation", weight=1.0, key_concepts=["Introduction", "Career Aspirations", "Role Interest"]),
            BlueprintTopic(name="Behavioral & Problem Solving", weight=1.0, key_concepts=["STAR Method", "Conflict Resolution", "Pressure & Teamwork"]),
        ],
        "Full Mock Interview (All Rounds)": [
            BlueprintTopic(name="Candidate Introduction & Resume Deep Dive", weight=1.0, key_concepts=["Self Introduction", "Project Highlights"]),
            BlueprintTopic(name="Technical Core & System Design", weight=1.5, key_concepts=["Core Architecture", "Frameworks", "Database Design"]),
            BlueprintTopic(name="Algorithms & CS Fundamentals", weight=1.2, key_concepts=["Complexity Analysis", "Data Structures", "OS & Networking"]),
            BlueprintTopic(name="Behavioral & Culture Fit", weight=1.0, key_concepts=["STAR Method", "Leadership & Values"]),
        ]
    },
    "Software Development Engineer (SDE)": {
        "Technical Round": [
            BlueprintTopic(name="Data Structures & Algorithms", weight=1.5, key_concepts=["Arrays", "Trees", "Graphs", "Dynamic Programming"]),
            BlueprintTopic(name="CS Fundamentals", weight=1.2, key_concepts=["OS Memory Management", "Networking TCP/IP", "DBMS Locking"]),
            BlueprintTopic(name="System Design & Architecture", weight=1.5, key_concepts=["API Design", "Scalability", "Caching", "Load Balancing"]),
        ],
        "HR & Behavioral Round": [
            BlueprintTopic(name="Professional Background & Communication", weight=1.0, key_concepts=["Communication Clarity", "Project Ownership"]),
            BlueprintTopic(name="Behavioral Scenarios", weight=1.0, key_concepts=["Handling Deadlines", "Overcoming Technical Blockers"]),
        ],
        "Full Mock Interview (All Rounds)": [
            BlueprintTopic(name="Introduction & Career Journey", weight=1.0, key_concepts=["Background", "Technical Passions"]),
            BlueprintTopic(name="DSA & System Design Deep Dive", weight=1.5, key_concepts=["Problem Solving", "Scalable Systems"]),
            BlueprintTopic(name="HR & Fit", weight=1.0, key_concepts=["Culture Fit", "Long-term Goals"]),
        ]
    }
}

COMPANY_PACKS: dict[str, list[BlueprintTopic]] = {
    "Amazon SDE-1": [
        BlueprintTopic(name="Amazon Leadership Principles & STAR Scenarios", weight=1.5, key_concepts=["Customer Obsession", "Ownership", "Bias for Action", "Have Backbone; Disagree & Commit"]),
        BlueprintTopic(name="Data Structures & Algorithmic Problem Solving", weight=1.5, key_concepts=["Trees", "Graphs", "Heaps", "Dynamic Programming", "Time/Space Complexity"]),
        BlueprintTopic(name="Low Level & Object-Oriented Design", weight=1.2, key_concepts=["Design Patterns", "SOLID Principles", "Class Diagrams", "Concurrency"]),
    ],
    "Google Software Engineer": [
        BlueprintTopic(name="Advanced Algorithms & Dynamic Programming", weight=1.6, key_concepts=["Graph Traversals", "DP Optimization", "Bit Manipulation", "Recursion & Backtracking"]),
        BlueprintTopic(name="System Scalability & Edge Cases", weight=1.4, key_concepts=["Distributed Systems", "API Design", "Rate Limiting", "Fault Tolerance"]),
        BlueprintTopic(name="Google Culture & Behavioral Assessment", weight=1.0, key_concepts=["Googleyness", "Ambiguity Resolution", "Peer Collaboration"]),
    ],
    "TCS NQT / Mass Recruiter": [
        BlueprintTopic(name="Core CS Fundamentals & Programming Syntax", weight=1.5, key_concepts=["Variables & Loops", "Array Operations", "Pointers/References", "Strings"]),
        BlueprintTopic(name="Database Management & SQL Queries", weight=1.3, key_concepts=["SQL Joins", "Normalization", "Primary/Foreign Keys", "Aggregate Functions"]),
        BlueprintTopic(name="HR, Communication & Aptitude", weight=1.0, key_concepts=["Self Introduction", "Strengths & Weaknesses", "Reasoning & Adaptability"]),
    ],
    "Infosys Specialist Engineer": [
        BlueprintTopic(name="Data Structures & Object-Oriented Programming", weight=1.5, key_concepts=["Stacks & Queues", "Linked Lists", "Encapsulation", "Polymorphism"]),
        BlueprintTopic(name="Web Technologies & Frameworks", weight=1.2, key_concepts=["HTML/CSS/JS", "REST APIs", "DBMS & CRUD", "Git Version Control"]),
        BlueprintTopic(name="Behavioral & Professional Readiness", weight=1.0, key_concepts=["Project Explanation", "Team Dynamics", "Role Motivation"]),
    ],
    "Product Manager": [
        BlueprintTopic(name="Product Sense & Design", weight=1.5, key_concepts=["User Pain Points", "Feature Prioritization", "Wireframing", "UI/UX Tradeoffs"]),
        BlueprintTopic(name="Product Metrics & Analytics", weight=1.4, key_concepts=["North Star Metric", "Retention & Churn", "A/B Testing", "Funnel Conversion"]),
        BlueprintTopic(name="Product Leadership & Communication", weight=1.1, key_concepts=["Cross-functional Collaboration", "Stakeholder Alignment", "Conflict Management"]),
    ],
    "Data Analyst / AI Engineer": [
        BlueprintTopic(name="Python Data Stack & SQL Analytics", weight=1.5, key_concepts=["Pandas", "NumPy", "Complex SQL Aggregations", "Data Cleaning"]),
        BlueprintTopic(name="Machine Learning & Applied Statistics", weight=1.3, key_concepts=["Regression & Classification", "Evaluation Metrics (F1/AUC)", "Hypothesis Testing"]),
        BlueprintTopic(name="Business Intelligence & Communication", weight=1.0, key_concepts=["Data Storytelling", "Dashboard Design", "Actionable Insights"]),
    ],
}


def get_blueprint(role: str, interview_type: str, company_pack: str | None = None) -> list[BlueprintTopic]:
    """Get topic list for a target role, company pack, and interview type with robust fallbacks."""
    if company_pack and company_pack in COMPANY_PACKS:
        return COMPANY_PACKS[company_pack]

    role_key = "Java Backend Developer" if "java" in role.lower() else "Software Development Engineer (SDE)"
    role_dict = ROLE_BLUEPRINTS.get(role_key, ROLE_BLUEPRINTS["Software Development Engineer (SDE)"])
    
    # Normalize interview_type
    normalized_type = interview_type
    if "Full" in interview_type:
        normalized_type = "Full Mock Interview (All Rounds)"
    elif "HR" in interview_type:
        normalized_type = "HR & Behavioral Round"
    elif "Technical" in interview_type:
        normalized_type = "Technical Round"

    topics = role_dict.get(normalized_type)
    if not topics:
        if "Full" in normalized_type:
            topics = [
                BlueprintTopic(name=f"{role} Introduction & Background", weight=1.0, key_concepts=["Self Introduction", "Resume Overview"]),
                BlueprintTopic(name=f"{role} Core Technical Competencies", weight=1.5, key_concepts=["Frameworks", "Data Structures", "System Design"]),
                BlueprintTopic(name="HR & Behavioral Evaluation", weight=1.0, key_concepts=["Behavioral Scenarios", "Teamwork", "Career Ambition"]),
            ]
        elif "HR" in normalized_type:
            topics = [
                BlueprintTopic(name="Behavioral & HR Evaluation", weight=1.0, key_concepts=["Self Introduction", "STAR Scenarios", "Conflict Resolution", "Salary & Expectations"]),
            ]
        else:
            topics = [
                BlueprintTopic(name=f"{role} Technical Fundamentals", weight=1.5, key_concepts=["Core Architecture", "Data Structures", "APIs", "Best Practices"]),
            ]
    return topics
