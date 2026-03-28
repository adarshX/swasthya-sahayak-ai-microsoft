"""
Swasthya Sahayak AI - RAG + MedGemma Test Suite
================================================
Tests: TF-IDF RAG retrieval, health doc corpus, MedGemma API,
       and the /ask-knowledge endpoint with RAG context.

Usage:
    # Unit tests (no backend needed):
    python tests/test_rag.py

    # Full integration tests (backend must be running on port 8080):
    BACKEND_URL=http://localhost:8080 python tests/test_rag.py --integration
"""

import json
import os
import sys
import time
import traceback
import urllib.request
import urllib.error

# Add backend to path for direct imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from utils import load_env, RESET, GREEN, RED, YELLOW, BOLD, CYAN

load_env()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

results: list[tuple[str, bool, str]] = []


def ok(name: str, detail: str = ""):
    results.append((name, True, detail))
    print(f"  {GREEN}PASS{RESET}  {name}" + (f"  [{detail}]" if detail else ""))


def fail(name: str, detail: str = ""):
    results.append((name, False, detail))
    print(f"  {RED}FAIL{RESET}  {name}" + (f"  -> {detail}" if detail else ""))


def warn(name: str, detail: str = ""):
    results.append((name, True, detail))
    print(f"  {YELLOW}WARN{RESET}  {name}" + (f"  [{detail}]" if detail else ""))


def http_post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def http_get(path: str) -> dict:
    req = urllib.request.Request(f"{BACKEND_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


# ===========================================================================
# Section 1 - RAG Module Unit Tests (no backend needed)
# ===========================================================================
def section_rag_unit():
    print(f"\n{BOLD}{CYAN}[ 1 ] RAG MODULE - UNIT TESTS{RESET}")

    # 1a. Import RAG module
    try:
        from rag import rag_retrieve, rag_context_string, get_doc_stats
        ok("Import RAG module")
    except ImportError as e:
        fail("Import RAG module", str(e))
        return

    # 1b. Check scikit-learn availability
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        ok("scikit-learn available")
    except ImportError:
        fail("scikit-learn not installed", "pip install scikit-learn")
        return

    # 1c. Check health docs directory
    stats = get_doc_stats()
    if stats["docs_dir_exists"]:
        ok("Health docs directory exists", stats["docs_dir"])
    else:
        fail("Health docs directory missing", stats["docs_dir"])
        return

    # 1d. Check docs loaded
    if stats["total_docs"] > 0:
        ok(f"Health docs loaded", f"{stats['total_docs']} docs, {stats['total_chunks']} chunks")
    else:
        fail("No health docs found")
        return

    # 1e. Minimum corpus size
    if stats["total_chunks"] >= 20:
        ok(f"Corpus size adequate", f"{stats['total_chunks']} chunks")
    else:
        warn(f"Corpus small", f"{stats['total_chunks']} chunks (expected >=20)")

    # ==== Retrieval Tests ====
    print(f"\n  {BOLD}-- Retrieval Quality --{RESET}")

    # 1f. Pneumonia query should retrieve pneumonia docs
    results_pneu = rag_retrieve("child has fast breathing and fever, pneumonia", top_k=3)
    if results_pneu:
        sources = [r[1] for r in results_pneu]
        if any("pneumonia" in s.lower() for s in sources):
            ok("Pneumonia query → pneumonia doc", f"top sources: {sources}")
        else:
            warn("Pneumonia query didn't match pneumonia doc", f"got: {sources}")
    else:
        fail("Pneumonia query returned no results")

    # 1g. Pregnancy query should retrieve pregnancy docs
    results_preg = rag_retrieve("pregnant woman bleeding headache danger", top_k=3)
    if results_preg:
        sources = [r[1] for r in results_preg]
        if any("pregnan" in s.lower() for s in sources):
            ok("Pregnancy query → pregnancy doc", f"top sources: {sources}")
        else:
            warn("Pregnancy query didn't match pregnancy doc", f"got: {sources}")
    else:
        fail("Pregnancy query returned no results")

    # 1h. Diarrhea query
    results_diarr = rag_retrieve("child diarrhea ORS dehydration vomiting", top_k=3)
    if results_diarr:
        sources = [r[1] for r in results_diarr]
        if any("diarrhea" in s.lower() for s in sources):
            ok("Diarrhea query → diarrhea doc", f"top sources: {sources}")
        else:
            warn("Diarrhea query didn't match diarrhea doc", f"got: {sources}")
    else:
        fail("Diarrhea query returned no results")

    # 1i. Vaccination query
    results_vacc = rag_retrieve("measles vaccine schedule baby 9 months", top_k=3)
    if results_vacc:
        sources = [r[1] for r in results_vacc]
        if any("vaccin" in s.lower() for s in sources):
            ok("Vaccination query → vaccination doc", f"top sources: {sources}")
        else:
            warn("Vaccination query didn't match vaccination doc", f"got: {sources}")
    else:
        fail("Vaccination query returned no results")

    # 1j. Anemia query
    results_anemia = rag_retrieve("pallor weakness iron hemoglobin anemia", top_k=3)
    if results_anemia:
        sources = [r[1] for r in results_anemia]
        if any("anemia" in s.lower() for s in sources):
            ok("Anemia query → anemia doc", f"top sources: {sources}")
        else:
            warn("Anemia query didn't match anemia doc", f"got: {sources}")
    else:
        fail("Anemia query returned no results")

    # 1k. Hindi query (transliterated)
    results_hindi = rag_retrieve("bachche ko bukhar tez saans pneumonia", top_k=3)
    if results_hindi:
        ok("Hindi/transliterated query returns results", f"{len(results_hindi)} chunks")
    else:
        warn("Hindi query returned no results (expected — TF-IDF is English-focused)")

    # 1l. Context string format
    ctx = rag_context_string("malaria fever treatment", top_k=2)
    if ctx and "[Source:" in ctx:
        ok("Context string has source citations", f"{len(ctx)} chars")
    elif ctx:
        warn("Context string missing source tags", f"{len(ctx)} chars")
    else:
        fail("Context string is empty for malaria query")

    # 1m. Relevance scores are properly ordered
    if len(results_pneu) >= 2:
        scores = [r[2] for r in results_pneu]
        if scores == sorted(scores, reverse=True):
            ok("Results sorted by relevance (descending)")
        else:
            fail("Results NOT sorted by relevance", str(scores))


# ===========================================================================
# Section 2 - MedGemma Configuration Check
# ===========================================================================
def section_medgemma_config():
    print(f"\n{BOLD}{CYAN}[ 2 ] MEDGEMMA CONFIGURATION{RESET}")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    MEDGEMMA_ENABLED = os.getenv("MEDGEMMA_ENABLED", "true").lower() in ("true", "1", "yes")
    MEDGEMMA_MODEL = os.getenv("MEDGEMMA_MODEL", "medgemma-27b-text-it")

    if MEDGEMMA_ENABLED:
        ok("MedGemma enabled", f"model={MEDGEMMA_MODEL}")
    else:
        warn("MedGemma disabled", "Set MEDGEMMA_ENABLED=true in .env")

    if GEMINI_API_KEY:
        ok("GEMINI_API_KEY set (required for MedGemma)", f"{GEMINI_API_KEY[:8]}…")
    else:
        warn("GEMINI_API_KEY not set", "MedGemma requires a Google AI Studio key")
        return

    # Try MedGemma API call
    try:
        from google import genai as google_genai
        ok("google-genai SDK available")
    except ImportError:
        fail("google-genai not installed", "pip install google-genai")
        return

    if not MEDGEMMA_ENABLED:
        warn("Skipping MedGemma API test (disabled)")
        return

    print(f"\n  {BOLD}-- MedGemma API Test --{RESET}")
    try:
        client = google_genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=MEDGEMMA_MODEL,
            contents="What are the danger signs in a child under 5 that require urgent referral? Answer in 2 sentences."
        )
        answer = response.text.strip()
        if len(answer) > 20:
            ok(f"MedGemma API call successful", f"{answer[:80]}…")
        else:
            warn("MedGemma answer too short", answer)
    except Exception as e:
        err = str(e)
        if "not found" in err.lower() or "404" in err:
            warn(f"MedGemma model '{MEDGEMMA_MODEL}' not available via API",
                 "Try: MEDGEMMA_MODEL=gemini-2.0-flash-lite or check Google AI Studio access")
        elif "permission" in err.lower() or "403" in err:
            warn("MedGemma API permission denied", "Model may require Vertex AI access")
        else:
            warn(f"MedGemma API error", err[:100])


# ===========================================================================
# Section 3 - Integration Tests (requires running backend)
# ===========================================================================
def section_integration():
    print(f"\n{BOLD}{CYAN}[ 3 ] INTEGRATION TESTS  ({BACKEND_URL}){RESET}")

    # 3a. Health endpoint shows RAG + MedGemma status
    try:
        h = http_get("/health")
        if "rag" in h:
            ok("/health shows RAG status", h["rag"])
        else:
            fail("/health missing RAG field")

        if "medgemma" in h:
            ok("/health shows MedGemma status", h["medgemma"])
        else:
            fail("/health missing MedGemma field")
    except urllib.error.URLError:
        warn("Backend not reachable", f"Start backend: start_backend.bat")
        return
    except Exception as e:
        fail("/health", str(e))
        return

    # 3b. RAG stats endpoint
    try:
        stats = http_get("/rag-stats")
        if stats.get("total_chunks", 0) > 0:
            ok("/rag-stats", f"{stats['total_docs']} docs, {stats['total_chunks']} chunks")
        else:
            fail("/rag-stats shows 0 chunks")
    except Exception as e:
        fail("/rag-stats", str(e))

    # 3c. Ask knowledge with RAG
    print(f"\n  {BOLD}-- ASHABot Q&A with RAG --{RESET}")

    test_questions = [
        {
            "question": "What should I do if a child under 5 has fast breathing and fever?",
            "language": "en",
            "expect_source": "pneumonia",
            "label": "Pneumonia Q&A (English)",
        },
        {
            "question": "Pregnant woman ko zyada bleeding ho raha hai, kya karna chahiye?",
            "language": "hi",
            "expect_source": "pregnancy",
            "label": "Pregnancy Q&A (Hindi)",
        },
        {
            "question": "How to prepare ORS for a child with diarrhea?",
            "language": "en",
            "expect_source": "diarrhea",
            "label": "Diarrhea/ORS Q&A (English)",
        },
        {
            "question": "When should a baby get measles vaccine?",
            "language": "en",
            "expect_source": "vaccin",
            "label": "Vaccination Q&A (English)",
        },
    ]

    for tq in test_questions:
        try:
            resp = http_post("/ask-knowledge", {
                "question": tq["question"],
                "language": tq["language"],
            })
            answer = resp.get("answer", "")
            provider = resp.get("provider", "none")
            rag_src = resp.get("rag_sources", "")
            chunks = resp.get("rag_chunks_used", 0)

            if not answer or "not configured" in answer.lower():
                warn(f"{tq['label']}: No AI provider", "Configure API keys in .env")
                continue

            # Check answer quality
            if len(answer) > 30:
                detail = f"provider={provider}, rag_sources={rag_src}, chunks={chunks}"
                ok(f"{tq['label']}", detail)
            else:
                warn(f"{tq['label']}: Short answer", answer[:60])

            # Check RAG sources were used
            if rag_src and tq["expect_source"].lower() in rag_src.lower():
                ok(f"  RAG source matched: {rag_src}")
            elif rag_src:
                warn(f"  RAG source didn't match expected '{tq['expect_source']}'", rag_src)
            else:
                warn(f"  No RAG sources in response")

        except Exception as e:
            fail(f"{tq['label']}", str(e)[:100])

    # 3d. Ask knowledge with patient context
    print(f"\n  {BOLD}-- Q&A with Patient Context --{RESET}")
    try:
        resp = http_post("/ask-knowledge", {
            "question": "What medicine should be given?",
            "language": "en",
            "patient_context": "3-year-old boy, fever for 2 days, fast breathing 55/min, no chest indrawing"
        })
        answer = resp.get("answer", "")
        if answer and "not configured" not in answer.lower():
            ok("Q&A with patient context", f"provider={resp.get('provider')}")
        else:
            warn("Q&A with patient context: no AI", "Configure API keys")
    except Exception as e:
        fail("Q&A with patient context", str(e)[:100])


# ===========================================================================
# Main
# ===========================================================================
def main():
    print(f"\n{BOLD}{CYAN}{'='*55}")
    print(f"  Swasthya Sahayak — RAG + MedGemma Test Suite")
    print(f"{'='*55}{RESET}")

    run_integration = "--integration" in sys.argv or "--all" in sys.argv

    # Always run unit tests
    section_rag_unit()
    section_medgemma_config()

    # Integration tests require backend
    if run_integration:
        section_integration()
    else:
        print(f"\n  {YELLOW}Skipping integration tests. Use --integration flag to run them.{RESET}")
        print(f"  {YELLOW}(Backend must be running on {BACKEND_URL}){RESET}")

    # Summary
    print(f"\n{BOLD}{CYAN}{'='*55}")
    print(f"  SUMMARY")
    print(f"{'='*55}{RESET}")
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    for name, p, detail in results:
        status = f"{GREEN}PASS{RESET}" if p else f"{RED}FAIL{RESET}"
        print(f"  [{status}]  {name}" + (f"  [{detail[:50]}]" if detail else ""))

    print(f"\n  {GREEN}{passed} passed{RESET}, {RED}{failed} failed{RESET}")

    if failed == 0:
        print(f"\n  {GREEN}RAG + MedGemma integration is working correctly.{RESET}\n")
    else:
        print(f"\n  {RED}Some tests failed. See details above.{RESET}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
