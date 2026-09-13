import base64
import binascii
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from . import llm, store  # noqa: E402  - after load_dotenv so the key is visible
from .api import chat, dashboard, path, profile, workspace  # noqa: E402
from .api.deps import goal_session  # noqa: E402
from .config import settings  # noqa: E402
from .engines import discovery  # noqa: E402
from .schemas import LearnerProfile  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="TESSA — Training & Education System for Skill Advancement",
    version="0.3.0",
    description="Training & Education System for Skill Advancement - Skill-graph based learning path generation with grounded explanations.",
)

allowed_origins_env = os.getenv("LPR_ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(path.router)
app.include_router(dashboard.router)
app.include_router(chat.router)
app.include_router(workspace.router)


# The browser holds the authoritative learner profile and sends it back on
# every call. On a serverless host the instance answering this request may
# never have seen this learner - see store.adopt for why that happens and why
# adopting is safe.
PROFILE_HEADER = "x-tessa-profile"
MAX_PROFILE_HEADER = 8192   # base64; a profile this large is not a real one


@app.middleware("http")
async def adopt_client_profile(request, call_next):
    raw = request.headers.get("x-tessa-profile") or request.headers.get("x-tessa-mentor-profile") or request.headers.get("x-aira-profile") or request.headers.get("x-orbit-profile")
    if raw and len(raw) <= MAX_PROFILE_HEADER:
        try:
            store.adopt(LearnerProfile.model_validate_json(base64.b64decode(raw)))
        except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
            # Untrusted input. A malformed header is not worth failing a
            # request over, but it should not pass silently either.
            log.warning("ignoring unusable %s header (%s)", PROFILE_HEADER, type(exc).__name__)
    return await call_next(request)


@app.get("/api/health")
def health():
    models = llm.configured_models()
    # The graph pool is ranked, so its first entry is the model actually
    # answering. Reporting a vendor name here was wrong as soon as the lane
    # stopped being Gemini-only, and the header reads this verbatim.
    graph = models["graph"]
    primary = graph[0] if graph else settings.model
    label = primary.split("/")[-1]
    return {
        "status": "ok",
        "catalog_mode": "per_goal",
        "courses": 0,
        "skills": 0,
        "roles": [],
        "llm": "live" if llm.available() else "offline",
        "search": "live" if discovery.available() else "offline",
        "model": f"{label} + {len(graph) - 1} fallbacks" if len(graph) > 1 else label,
        "primary_model": primary,
        "models": models,
    }


@app.get("/api/catalog/roles")
def roles(learner_id: str | None = None):
    if not learner_id:
        return []
    return workspace.catalog_payload(goal_session(learner_id))["roles"]


@app.get("/api/catalog/courses")
def courses(learner_id: str | None = None, q: str = "", limit: int = 50):
    if not learner_id:
        return []
    cat = goal_session(learner_id).catalog
    items = cat.courses
    if q:
        needle = q.lower()
        items = [c for c in items if needle in c.title.lower() or needle in c.description.lower()]
    return [c.model_dump() for c in items[:limit]]


@app.get("/api/catalog/skills")
def skills(learner_id: str | None = None):
    if not learner_id:
        return []
    return [s.model_dump() for s in goal_session(learner_id).catalog.skills]


# The UI is one self-contained file with no build step - no npm, no bundler,
# nothing to install before a judge can open it. Mounted last so it cannot
# shadow an /api route.
STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
