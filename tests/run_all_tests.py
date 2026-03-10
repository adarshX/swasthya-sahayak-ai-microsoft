"""
Master test runner — runs all Azure service tests in sequence.
Run from repo root:  python tests/run_all_tests.py
"""

import subprocess
import sys
import os

TESTS = [
    ("Blob Storage",  "tests/test_blob_storage.py"),
    ("OpenAI",        "tests/test_openai.py"),
    ("Speech",        "tests/test_speech.py"),
]

PASS_COLOR = "\033[92m"
FAIL_COLOR = "\033[91m"
HEAD_COLOR = "\033[1;96m"
RESET      = "\033[0m"

def main():
    print(f"\n{HEAD_COLOR}{'='*50}")
    print(f"  Swasthya Sahayak — Azure Services Test Suite")
    print(f"{'='*50}{RESET}\n")

    # Check we're in repo root
    if not os.path.exists(".env"):
        print("\033[91m  .env file not found. Run from repo root directory.\033[0m")
        sys.exit(1)

    summary = []
    for name, script in TESTS:
        print(f"{HEAD_COLOR}--- {name} ---{RESET}")
        result = subprocess.run([sys.executable, script], capture_output=False)
        passed = result.returncode == 0
        summary.append((name, passed))
        print()

    print(f"{HEAD_COLOR}{'='*50}")
    print(f"  SUMMARY")
    print(f"{'='*50}{RESET}")
    for name, passed in summary:
        status = f"{PASS_COLOR}PASS{RESET}" if passed else f"{FAIL_COLOR}FAIL{RESET}"
        print(f"  [{status}]  {name}")

    all_passed = all(p for _, p in summary)
    print()
    if all_passed:
        print(f"{PASS_COLOR}  All Azure services are configured correctly.{RESET}")
        print(f"  You are ready to run the full app.\n")
    else:
        failed = [n for n, p in summary if not p]
        print(f"{FAIL_COLOR}  Fix the failing services: {', '.join(failed)}{RESET}\n")
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
