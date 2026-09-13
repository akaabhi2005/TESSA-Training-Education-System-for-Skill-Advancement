"""Production Readiness & Health Verification Script for TESSA.

Run this script to validate environment keys, cache write permissions, Tavily
search connection, Gemini LLM client connectivity, and retrieval configuration
before deploying to production.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend root is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CACHE_DIR, settings
from app import llm
from app.engines import discovery, retrieval
from app.catalog import Catalog
from app.engines.goal import GoalSpec
from app.schemas import Course


def main():
    print("==========================================================")
    print("   TESSA — Production Readiness & Technical Audit Check   ")
    print("==========================================================")
    
    passed = True

    # 1. Environment & API Keys Check
    print("\n1. ENVIRONMENT & API CREDENTIALS:")
    if settings.gemini_api_key:
        print(f"  [OK] GEMINI_API_KEY: Present ({settings.gemini_api_key[:6]}...)")
    else:
        print("  [FAIL] GEMINI_API_KEY: Missing! New goals will fail.")
        passed = False

    if settings.tavily_api_key:
        print(f"  [OK] TAVILY_API_KEY: Present ({settings.tavily_api_key[:6]}...)")
    else:
        print("  [WARN] TAVILY_API_KEY: Missing! Web search discovery will run in offline mode.")

    print(f"  [INFO] Primary LLM Model: {settings.model}")
    print(f"  [INFO] App Offline Mode: {settings.offline}")

    # 2. Cache Permissions Check
    print("\n2. CACHE DIRECTORY PERMISSIONS:")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        test_file = CACHE_DIR / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        print(f"  [OK] Cache Directory writable: {CACHE_DIR}")
    except Exception as exc:
        print(f"  [FAIL] Cache Directory not writable ({CACHE_DIR}): {exc}")
        passed = False

    # 3. LLM Client Connection Check
    print("\n3. LLM ENGINE CONNECTIVITY:")
    client = llm._get_client()
    if client:
        print("  [OK] Google GenAI Client initialized successfully.")
    else:
        print("  [FAIL] Google GenAI Client failed to initialize.")
        passed = False

    # 4. Search Discovery Check
    print("\n4. WEB SEARCH DISCOVERY CONNECTIVITY:")
    if discovery.available():
        print("  [OK] Tavily Search Discovery: Active & Available.")
    else:
        print("  [WARN] Tavily Search Discovery: Inactive / Offline.")

    # 5. Retrieval & Scoring Check
    print("\n5. RETRIEVAL & SCORING ENCODERS:")
    try:
        sample_course = Course(
            id="c_test",
            title="Test Python Course",
            provider="Test Provider",
            url="https://example.com/course",
            description="Learn Python basics",
            level="beginner",
            hours=5.0,
            format="video",
            teaches={"python": 1.0}
        )
        cat = Catalog(skills=[], courses=[sample_course], roles=[])
        retriever = retrieval.Retriever(cat)
        if retriever.encoder:
            print("  [OK] Dense Encoder: sentence-transformers (BAAI/bge-small-en-v1.5)")
        else:
            print("  [OK] Fallback Encoder: TF-IDF Vectorizer (Fast & Lightweight)")
    except Exception as exc:
        print(f"  [FAIL] Retriever initialization error: {exc}")
        passed = False

    print("\n==========================================================")
    if passed:
        print("  RESULT: PRODUCTION READINESS AUDIT PASSED [OK]")
    else:
        print("  RESULT: PRODUCTION READINESS AUDIT ENCOUNTERED ISSUES [FAIL]")
    print("==========================================================")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
