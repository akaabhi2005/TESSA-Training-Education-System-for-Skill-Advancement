TESSA — Training & Education System for Skill Advancement

TESSA is an AI-driven adaptive learning system that creates personalized learning roadmaps based on a learner's goal, current skills, available time, preferences, and progress.

Unlike fixed-course recommenders, TESSA does not force every learner into the same predefined path. It builds a skill graph for the chosen goal, discovers relevant learning resources from the live web, identifies skill gaps, and creates a prerequisite-aware roadmap using deterministic planning algorithms.

AI understands. Algorithms decide.

✨ Key Features

Personalized Learning Roadmaps
Generates a roadmap for almost any learning goal.

Skill Graph & Prerequisites
Breaks a goal into required skills and arranges them in the correct learning order.

Live Resource Discovery
Uses Tavily to discover real courses, tutorials, documentation, and learning resources from the web.

Skill Gap Analysis
Compares the learner's current mastery with the skills required for the target goal.

Adaptive Diagnostics
Uses quizzes and learner evidence to improve mastery estimates.

Deterministic Planning
Uses budgeted coverage and prerequisite-aware ordering instead of letting an LLM randomly decide the final roadmap.

Explainable Recommendations
Explains why a resource was selected and why another resource may not be included.

What-If Simulator
Lets learners change available hours or learning duration and preview how the roadmap changes.

Progress Tracking
Tracks completed learning resources, milestones, and learner readiness.

AI Learning Assistant
Provides contextual guidance using the learner's active roadmap and progress.

🧠 How TESSA Works

User Goal + Constraints
        ↓
Goal Understanding
        ↓
Skill Graph Generation
        ↓
Live Resource Discovery
        ↓
Learner Mastery Profile
        ↓
Skill Gap Analysis
        ↓
Resource Ranking
        ↓
Budgeted Course Selection
        ↓
Prerequisite-Aware Ordering
        ↓
Personalized Roadmap
        ↓
Progress / Feedback / Diagnostic
        ↓
Adaptive Replanning

The core idea is simple:

AI is used for understanding goals, interpreting resources, explanations, and assistance.

Algorithms are used for selecting, ordering, and validating the learning path.

This makes the roadmap more auditable, explainable, and testable.


Architecture in Simple Words

                     ┌─────────────────────┐
                     │        USER         │
                     │ Goal + Constraints  │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │      FRONTEND       │
                     │ HTML / CSS / JS     │
                     └──────────┬──────────┘
                                │
                                ▼
                     ┌─────────────────────┐
                     │   FASTAPI BACKEND   │
                     └──────────┬──────────┘
                                │
               ┌────────────────┼────────────────┐
               ▼                ▼                ▼
        ┌────────────┐   ┌──────────────┐  ┌──────────────┐
        │   Gemini   │   │    Tavily    │  │Learner Model │
        │ Skill DAG  │   │ Live Search  │  │ + Diagnostic │
        └──────┬─────┘   └──────┬───────┘  └──────┬───────┘
               │                │                 │
               └──────────┬─────┴──────────┬──────┘
                          ▼                ▼
                   ┌──────────────┐  ┌──────────────┐
                   │ Skill Gaps   │  │Resource Pool │
                   └──────┬───────┘  └──────┬───────┘
                          └──────────┬───────┘
                                     ▼
                           ┌───────────────────┐
                           │  Hybrid Ranking   │
                           │ BM25 / TF-IDF     │
                           └─────────┬─────────┘
                                     ▼
                           ┌───────────────────┐
                           │Deterministic      │
                           │Planner            │
                           │Set Cover + Budget │
                           └─────────┬─────────┘
                                     ▼
                           ┌───────────────────┐
                           │Topological Sort   │
                           └─────────┬─────────┘
                                     ▼
                           ┌───────────────────┐
                           │Personalized Route │
                           │Phases + Projects  │
                           └─────────┬─────────┘
                                     │
                                     ▼
                           Progress / Feedback
                                     │
                                     └──────► Replan


Workflow Explained


Goal Intake — Learner enters a free-text goal, available hours, timeline, budget, and preferences.

Skill Graph Generation — Gemini converts the goal into skills and prerequisite relationships.

Live Discovery — Tavily finds relevant real-world courses, tutorials, and documentation.

Learner Profiling — TESSA combines stated skills, learning history, diagnostics, and progress.

Skill Gap Analysis — Current mastery is compared with required target mastery.

Resource Ranking — Candidate resources are ranked using relevance, gap coverage, level fit, and preferences.

Budgeted Selection — The planner selects useful resources within available learning time.

Topological Ordering — Prerequisites are placed before advanced topics.

Roadmap Creation — Selected resources are grouped into phases with projects and checkpoints.

Explainability — TESSA shows why a resource was selected or omitted.

Adaptive Replanning — Progress, diagnostics, and feedback update the learner model and roadmap.

TESSA is not designed to generate one static roadmap and stop. The learner model evolves as the user studies, completes resources, takes diagnostics, or gives feedback.



🛠️ Tech Stack

Frontend

HTML5

CSS3

Vanilla JavaScript

Backend

Python

FastAPI

Pydantic

Uvicorn

AI & Search

Google Gemini API

Tavily Search API

Optional OpenAI-compatible model routing

Ranking & Planning

BM25

TF-IDF / Semantic Retrieval

Reciprocal Rank Fusion

NetworkX

NumPy

scikit-learn

Budgeted Set-Cover / Maximum-Coverage style planning

Topological Sorting

Deployment & State

Vercel

JSON / process-local prototype state

Browser-managed learner profile state


## Project Blueprint

```text
                         ┌──────────────────────────────┐
                         │        USER / LEARNER        │
                         │ Goal • Skills • Time • Level │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
┌───────────────────────────────────────────────────────┐
│                 1. USER INTAKE LAYER                  │
│                                                       │
│ Profile → Career Goal → Existing Skills → Time        │
│ Budget → Preferred Learning Style                     │
└──────────────────────────┬────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────┐
│              2. AI GOAL UNDERSTANDING                 │
│                                                       │
│                 Gemini / LLM Engine                   │
│                                                       │
│ Goal Parsing → Skill Extraction → Classification      │
└──────────────────────────┬────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────┐
│                3. SKILL GRAPH ENGINE                  │
│                                                       │
│ Skill A ─────► Skill B                                │
│    │              │                                   │
│    ▼              ▼                                   │
│ Skill C ─────► Skill D                                │
│                                                       │
│ DAG • Prerequisites • Dependency Validation           │
│ Topological Ordering                                  │
└──────────────────────────┬────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────┐
│                 4. DIAGNOSTIC ENGINE                  │
│                                                       │
│ Questions → User Answers → Knowledge Detection        │
│                       │                               │
│                       ▼                               │
│                 Mastery Score                         │
└──────────────────────────┬────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────┐
│              5. ADAPTIVE ROADMAP ENGINE               │
│                                                       │
│ Skill Graph + Diagnostic + Time + Constraints         │
│                       │                               │
│                       ▼                               │
│            Personalized Learning Path                 │
│                                                       │
│ Week 1 → Week 2 → Week 3 → Project → Assessment      │
└──────────────────────────┬────────────────────────────┘
                           │
               ┌───────────┴───────────┐
               │                       │
               ▼                       ▼
┌───────────────────────────┐   ┌───────────────────────┐
│  6. RESOURCE DISCOVERY    │   │ 7. LEARNING WORKSPACE │
│                           │   │                       │
│ Tavily / Live Web Search  │   │ Tasks                 │
│          │                │   │ Notes                 │
│          ▼                │   │ Progress              │
│ Courses • Videos • Docs   │   │ Assessments           │
│ Practice Problems         │   │ Current Skill         │
│          │                │   │ Completion            │
│          ▼                │   │                       │
│ BM25 / TF-IDF Ranking     │   └───────────┬───────────┘
└─────────────┬─────────────┘               │
              └───────────────┬─────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────┐
│                8. MASTERY TRACKING                    │
│                                                       │
│ Quiz + Task + Project + Activity                      │
│                       │                               │
│                       ▼                               │
│              Mastery Evaluation                       │
│                       │                               │
│                       ▼                               │
│ Not Started • Learning • Mastered                     │
└──────────────────────────┬────────────────────────────┘
                           │
                           ▼
                ┌────────────────────────┐
                │   ROADMAP ADAPTATION   │
                │                        │
                │ Weak Skill Found?      │
                │ New Goal?              │
                │ Skill Mastered?        │
                │ Resource Outdated?     │
                └───────────┬────────────┘
                            │
                            └──────► Roadmap Engine
```
                  

🎯 What Makes TESSA Different?

Traditional learning platforms usually recommend from a fixed internal catalogue.

TESSA instead starts with:

What does this learner need to learn next to reach this goal within their constraints?

Its main differentiators are:

Dynamic goal-to-skill decomposition

Live web-grounded learning resources

Learner-specific skill-gap analysis

Deterministic roadmap planning

Prerequisite-safe ordering

Explainable recommendations

Adaptive replanning based on progress and diagnostics


🔮 Future Scope

Planned extensions include:

PostgreSQL / Supabase-based persistent storage

Authentication and multi-device learner accounts

Verified resource quality signals

Job-role and industry skill mapping

Placement Hub

AI Mock Interviews

Interview performance analysis

Interview-based skill-gap detection

Live job recommendations

Resume-based interview preparation

Long-term learner analytics

Mobile application

💡 Vision

TESSA aims to become more than a course recommender.

The long-term goal is to create a complete system that helps a learner:

Learn → Practice → Validate → Improve → Prepare for Interviews → Match with Opportunities

📌 Project Name

TESSA
Training & Education System for Skill Advancement

📄 License

This project is currently intended for educational, academic, and prototype use.

