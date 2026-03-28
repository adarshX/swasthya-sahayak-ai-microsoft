"""
Protocol Compiler — converts YAML protocol definitions to compiled JSON.
Reads all .yaml files from protocols/ directory and outputs protocols.json.
Also copies the compiled output to the Android app assets folder.

Usage:
    cd protocol-engine
    pip install pyyaml   # one-time
    python compile_protocols.py
"""

import json
import os
import glob
from datetime import datetime

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml")
    exit(1)

PROTOCOLS_DIR = os.path.join(os.path.dirname(__file__), "protocols")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "protocols.json")
ANDROID_ASSETS = os.path.join(
    os.path.dirname(__file__), "..", "android-app", "app", "src", "main", "assets", "protocols.json"
)


def compile_protocols():
    yaml_files = sorted(glob.glob(os.path.join(PROTOCOLS_DIR, "*.yaml")))
    if not yaml_files:
        print(f"No .yaml files found in {PROTOCOLS_DIR}")
        return

    conditions = []
    for yaml_file in yaml_files:
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        condition = {
            "id": data["condition"],
            "condition": data["condition"],
            "version": data.get("version", ""),
            "patient_age_max_months": data.get("patient_age_max_months", 0),
            "requires_pregnant": data.get("requires_pregnant", False),
            "triggers": data.get("triggers", []),
            "risk_modifiers": data.get("risk_modifiers", []) or [],
            "thresholds": data.get("thresholds", {}),
            "rationale": data.get("rationale", ""),
            "follow_up_questions": data.get("follow_up_questions", []) or [],
        }
        conditions.append(condition)
        print(f"  Compiled: {os.path.basename(yaml_file)} -> {condition['id']}")

    output = {
        "version": "1.0",
        "compiled_at": datetime.now().isoformat(),
        "conditions": conditions,
    }

    # Write to protocol-engine/
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWritten: {OUTPUT_FILE}")

    # Copy to Android assets
    os.makedirs(os.path.dirname(ANDROID_ASSETS), exist_ok=True)
    with open(ANDROID_ASSETS, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Copied:  {ANDROID_ASSETS}")


if __name__ == "__main__":
    print("Compiling WHO-IMNCI / NHM protocols...\n")
    compile_protocols()
    print("\nDone. protocols.json is ready for Android build.")
