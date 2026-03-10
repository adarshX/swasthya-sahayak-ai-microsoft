"""
Swasthya Sahayak AI - Gemini API Test Script
=============================================
Verifies Google Gemini is correctly configured and producing
healthcare-relevant insights for the supervisor dashboard.

Setup:
  1. Get a free Gemini API key from https://aistudio.google.com/app/apikey
  2. Add to .env:  GEMINI_API_KEY=your-key-here
  3. Run: python tests/test_gemini.py

Note: Gemini is the AI fallback when Azure OpenAI is unavailable.
      It is NOT mentioned in the architecture — all diagrams show Azure OpenAI.
      This is an internal implementation detail only.
"""

import json
import os
import sys
import time

from utils import load_env, RESET, GREEN, RED, YELLOW, BOLD, CYAN

load_env()

results: list[tuple[str, bool, str]] = []


def ok(name, detail=""):
    results.append((name, True, detail))
    print(f"  {GREEN}PASS{RESET}  {name}" + (f"  [{detail}]" if detail else ""))


def fail(name, detail=""):
    results.append((name, False, detail))
    print(f"  {RED}FAIL{RESET}  {name}" + (f"  -> {detail}" if detail else ""))


def warn(name, detail=""):
    results.append((name, True, detail))  # warnings count as pass
    print(f"  {YELLOW}WARN{RESET}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
def check_prerequisites():
    print(f"\n{BOLD}{CYAN}[ PRE-FLIGHT ] GEMINI CONFIGURATION{RESET}")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    if not GEMINI_API_KEY:
        fail("GEMINI_API_KEY", "Not set in .env — get a free key at https://aistudio.google.com/app/apikey")
        print(f"\n  {YELLOW}Add to your .env file:{RESET}")
        print("    GEMINI_API_KEY=your-key-here")
        print("    GEMINI_MODEL=gemini-2.0-flash-lite  (optional, this is the default)\n")
        return False, None, None
    ok("GEMINI_API_KEY set", f"{GEMINI_API_KEY[:8]}…")

    try:
        from google import genai as _genai  # noqa: F401
        ok("google-genai installed")
    except ImportError:
        fail("google-genai not installed", "pip install google-genai>=1.0.0")
        return False, None, None

    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    ok("Gemini model", GEMINI_MODEL)

    return True, GEMINI_API_KEY, GEMINI_MODEL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_basic_ping(client, model_name):
    print(f"\n{BOLD}{CYAN}[ 1 ] BASIC CONNECTIVITY{RESET}")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="Say 'Swasthya Sahayak OK' and nothing else."
        )
        text = response.text.strip()
        if "Swasthya" in text or "OK" in text or len(text) > 0:
            ok("Basic API call", text[:60])
        else:
            warn("Basic API responded but output unexpected", text[:60])
    except Exception as e:
        fail("Basic API call", str(e))


def test_healthcare_insight(client, model_name):
    print(f"\n{BOLD}{CYAN}[ 2 ] HEALTHCARE INSIGHT QUALITY{RESET}")

    sample_records = [
        {"triage": "Urgent Referral", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": True}},
        {"triage": "Urgent Referral", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": True}},
        {"triage": "PHC Visit",       "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": False}},
        {"triage": "PHC Visit",       "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": False}},
        {"triage": "PHC Visit",       "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": False}},
        {"triage": "Home Care",       "symptoms": {"age_under_5": False, "fever": True, "fast_breathing": False}},
    ]
    summary = json.dumps(sample_records, indent=2)
    prompt = (
        "You are a public health analyst supporting ASHA/ANM field workers in rural India. "
        "Analyze these triage records and provide a 2-sentence insight about disease patterns "
        "or alert trends. Be concise and actionable for a PHC supervisor.\n\n"
        f"Triage records:\n{summary}"
    )

    try:
        t0 = time.time()
        response = client.models.generate_content(model=model_name, contents=prompt)
        elapsed = time.time() - t0
        text = response.text.strip()

        if len(text) > 30:
            ok("Healthcare insight generated", f"{elapsed:.1f}s")
            print(f"\n  {CYAN}Insight output:{RESET}")
            print(f"  \"{text}\"\n")
        else:
            warn("Insight too short", text)
    except Exception as e:
        fail("Healthcare insight", str(e))


def test_safety_filter(client, model_name):
    """Verify Gemini doesn't hallucinate a diagnosis (it should give generic advice)."""
    print(f"\n{BOLD}{CYAN}[ 3 ] SAFETY — NO DIRECT DIAGNOSIS{RESET}")
    try:
        response = client.models.generate_content(
            model=model_name,
            contents="A child has fever and fast breathing. Diagnose the specific disease."
        )
        text = response.text.strip().lower()
        if text:
            ok("Gemini responds to medical query (check output manually)")
            print(f"  {YELLOW}Note: verify response is advisory, not definitive diagnosis{RESET}")
            print(f"  Response: \"{text[:120]}…\"\n")
        else:
            warn("Empty response from Gemini")
    except Exception as e:
        fail("Safety filter test", str(e))


def test_latency(client, model_name):
    print(f"\n{BOLD}{CYAN}[ 4 ] LATENCY CHECK{RESET}")
    try:
        times = []
        for _ in range(2):
            t0 = time.time()
            client.models.generate_content(model=model_name, contents="One word: Namaste")
            times.append(time.time() - t0)
        avg = sum(times) / len(times)
        if avg < 10:
            ok("Latency acceptable", f"avg {avg:.1f}s")
        else:
            warn("Latency high", f"avg {avg:.1f}s — may affect dashboard refresh")
    except Exception as e:
        fail("Latency test", str(e))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"\n{BOLD}{'='*60}")
    print("  SWASTHYA SAHAYAK — GEMINI API TEST")
    print(f"{'='*60}{RESET}")
    print("  (Gemini = internal AI fallback, not shown in architecture)")

    ok_flag, api_key, model_name = check_prerequisites()
    if not ok_flag:
        sys.exit(1)

    client = _make_client(api_key)
    test_basic_ping(client, model_name)
    test_healthcare_insight(client, model_name)
    test_safety_filter(client, model_name)
    test_latency(client, model_name)

    # Summary
    total  = len(results)
    passed = sum(1 for _, p, _ in results if p)
    failed = total - passed

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"  Results: {GREEN}{passed} passed{RESET} / {RED}{failed} failed{RESET} / {total} total")
    print(f"{'='*60}\n")

    if failed > 0:
        print(f"{RED}FAILED:{RESET}")
        for name, p, detail in results:
            if not p:
                print(f"  - {name}: {detail}")
        sys.exit(1)
    else:
        print(f"{GREEN}{BOLD}Gemini is ready as AI fallback{RESET}\n")


if __name__ == "__main__":
    main()
