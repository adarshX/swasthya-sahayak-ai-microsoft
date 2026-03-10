"""
TEST: Azure OpenAI (or direct OpenAI API)
Run:  python tests/test_openai.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

from utils import load_env, PASS, FAIL, INFO, WARN

load_env()

# Supports both env var names (AZURE_OPENAI_API_KEY is the Azure SDK standard;
# AZURE_OPENAI_KEY is what we set in .env — check both)
OPENAI_API_KEY          = os.getenv("OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AZURE_OPENAI_KEY        = os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
OPENAI_MODEL            = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_VERSION             = "2024-08-01-preview"


def list_azure_deployments(endpoint, key):
    """Call REST API to list what model deployments actually exist."""
    url = f"{endpoint}/openai/deployments?api-version={API_VERSION}"
    req = urllib.request.Request(url, headers={"api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return [d["id"] for d in data.get("data", [])]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"HTTP {e.code}: {body}")


def main():
    print("\n=== OpenAI / Azure OpenAI Test ===\n")

    try:
        from openai import OpenAI, AzureOpenAI
    except ImportError:
        print(f"{FAIL}  openai package not installed -> run: pip install openai")
        sys.exit(1)

    # --- Determine provider ---
    if OPENAI_API_KEY:
        print(f"{INFO}  Using: Direct OpenAI API (openai.com)")
        print(f"{INFO}  Model: {OPENAI_MODEL}")
        client = OpenAI(api_key=OPENAI_API_KEY)
        model  = OPENAI_MODEL

    elif AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY:
        print(f"{INFO}  Using: Azure OpenAI")
        print(f"{INFO}  Endpoint:   {AZURE_OPENAI_ENDPOINT}")
        print(f"{INFO}  Deployment: {AZURE_OPENAI_DEPLOYMENT}")
        print(f"{INFO}  API version: {API_VERSION}\n")

        # --- Pre-flight: list actual deployments before trying to call ---
        print(f"{INFO}  Checking what deployments exist in your resource...")
        try:
            deployments = list_azure_deployments(AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY)
            if deployments:
                print(f"{PASS}  Found {len(deployments)} deployment(s): {deployments}")
                if AZURE_OPENAI_DEPLOYMENT not in deployments:
                    print(f"{WARN}  '{AZURE_OPENAI_DEPLOYMENT}' is NOT in the list above!")
                    print(f"       -> Either deploy that model, or update AZURE_OPENAI_DEPLOYMENT")
                    print(f"          in .env to one of: {deployments}")
                    print(f"\n       HOW TO DEPLOY: see instructions printed below.\n")
                    _print_deployment_steps(AZURE_OPENAI_ENDPOINT)
                    sys.exit(1)
                else:
                    print(f"{PASS}  Deployment '{AZURE_OPENAI_DEPLOYMENT}' exists\n")
            else:
                print(f"{WARN}  No deployments found in this resource!")
                print(f"       You must deploy a model before using the API.\n")
                _print_deployment_steps(AZURE_OPENAI_ENDPOINT)
                sys.exit(1)
        except Exception as e:
            print(f"{FAIL}  Could not list deployments -> {e}")
            print(f"       Check your endpoint URL and key are correct.")
            sys.exit(1)

        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version=API_VERSION,
        )
        model = AZURE_OPENAI_DEPLOYMENT

    else:
        print(f"{FAIL}  No credentials found in .env")
        print(f"       Option A: set OPENAI_API_KEY (direct openai.com, no approval)")
        print(f"       Option B: set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY (Azure)")
        sys.exit(1)

    results = []

    # Test 1: Simple ping
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
        _print_error_hint(str(e))
        results.append(False)

    # Test 2: Case intelligence prompt (same as what the app sends)
    print()
    try:
        sample_records = [
            {"triage": "Urgent Referral", "symptoms": {"age_under_5": True,  "fever": True,  "fast_breathing": True}},
            {"triage": "PHC Visit",       "symptoms": {"age_under_5": True,  "fever": True,  "fast_breathing": False}},
            {"triage": "Home Care",       "symptoms": {"age_under_5": False, "fever": True,  "fast_breathing": False}},
        ]
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
        print(f"\n       Sample AI insight:")
        print(f"       \"{insight}\"\n")
        results.append(True)
    except Exception as e:
        _print_error_hint(str(e))
        results.append(False)

    print(f"{'='*40}")
    passed = sum(results)
    print(f"  Result: {passed}/{len(results)} checks passed")
    if passed == len(results):
        print(f"\033[92m  Azure OpenAI is correctly configured.\033[0m\n")
    else:
        print(f"\033[91m  OpenAI has issues — check errors above.\033[0m\n")


def _print_error_hint(error: str):
    hints = {
        "503": "503 = model deployment not found or not ready. Check deployment name in .env matches exactly.",
        "404": "404 = deployment name wrong or endpoint URL wrong.",
        "401": "401 = API key is invalid or expired.",
        "429": "429 = rate limit / quota exceeded.",
        "DeploymentNotFound": "Deployment name in AZURE_OPENAI_DEPLOYMENT doesn't match what's in your resource.",
    }
    print(f"{FAIL}  API call failed -> {error}")
    for key, hint in hints.items():
        if key in error:
            print(f"{WARN}  Hint: {hint}")
            break


def _print_deployment_steps(endpoint: str):
    resource = endpoint.replace("https://", "").replace(".openai.azure.com", "")
    print(f"""
  HOW TO DEPLOY A MODEL IN AZURE AI FOUNDRY
  ------------------------------------------
  1. Go to: https://ai.azure.com
  2. Sign in with your Azure account
  3. Top nav -> click your project, or create one linked to '{resource}'
  4. Left sidebar -> "Models + endpoints"
  5. Click "+ Deploy model" -> "Deploy base model"
  6. Search for: gpt-4o  (or gpt-4o-mini if gpt-4o not available)
  7. Click "Confirm"
  8. Deployment name: type exactly  gpt-4o  (this goes in AZURE_OPENAI_DEPLOYMENT)
  9. Click "Deploy" -> wait ~1 min for status to show "Succeeded"
  10. Come back and re-run: python tests/test_openai.py
""")


if __name__ == "__main__":
    main()
