"""
TEST: Azure OpenAI (or direct OpenAI API)
Checks: credentials valid, model reachable, actual completion works
Run:  python tests/test_openai.py
"""

import os
import sys

def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

load_env()

OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
OPENAI_MODEL            = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"
WARN = "\033[93m  WARN\033[0m"

def main():
    print("\n=== OpenAI / Azure OpenAI Test ===\n")

    try:
        from openai import OpenAI, AzureOpenAI
    except ImportError:
        print(f"{FAIL}  openai package not installed -> run: pip install openai")
        sys.exit(1)

    # Determine which provider to use
    if OPENAI_API_KEY:
        print(f"{INFO}  Using: Direct OpenAI API (openai.com)")
        print(f"{INFO}  Model: {OPENAI_MODEL}")
        client = OpenAI(api_key=OPENAI_API_KEY)
        model  = OPENAI_MODEL
    elif AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY:
        print(f"{INFO}  Using: Azure OpenAI")
        print(f"{INFO}  Endpoint: {AZURE_OPENAI_ENDPOINT}")
        print(f"{INFO}  Deployment: {AZURE_OPENAI_DEPLOYMENT}")
        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version="2024-02-01",
        )
        model = AZURE_OPENAI_DEPLOYMENT
    else:
        print(f"{FAIL}  No AI credentials found in .env")
        print(f"       Set OPENAI_API_KEY  (direct OpenAI, no approval needed)")
        print(f"       OR set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY  (Azure OpenAI)")
        sys.exit(1)

    results = []

    # Test 1: Simple completion
    print()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=5,
        )
        reply = response.choices[0].message.content.strip()
        print(f"{PASS}  API call succeeded -> model replied: '{reply}'")
        results.append(True)
    except Exception as e:
        print(f"{FAIL}  API call failed -> {e}")
        results.append(False)

    # Test 2: Case intelligence prompt (exactly what the app sends)
    print()
    try:
        sample_records = [
            {"triage": "Urgent Referral", "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": True}},
            {"triage": "PHC Visit",       "symptoms": {"age_under_5": True, "fever": True, "fast_breathing": False}},
            {"triage": "Home Care",       "symptoms": {"age_under_5": False,"fever": True, "fast_breathing": False}},
        ]
        import json
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a public health analyst. Analyze these triage records from a "
                        "rural India PHC and give a 2-sentence insight about disease patterns. "
                        "Be concise and actionable for a field supervisor."
                    ),
                },
                {"role": "user", "content": json.dumps(sample_records, indent=2)},
            ],
            max_tokens=150,
        )
        insight = response.choices[0].message.content.strip()
        print(f"{PASS}  Case intelligence prompt works")
        print(f"       Sample insight:\n       \"{insight}\"\n")
        results.append(True)
    except Exception as e:
        print(f"{FAIL}  Case intelligence prompt failed -> {e}")
        results.append(False)

    print(f"{'='*35}")
    passed = sum(results)
    print(f"  Result: {passed}/{len(results)} checks passed")
    if passed == len(results):
        print(f"\033[92m  OpenAI is correctly configured.\033[0m\n")
    else:
        print(f"\033[91m  OpenAI has issues — check errors above.\033[0m\n")

if __name__ == "__main__":
    main()
