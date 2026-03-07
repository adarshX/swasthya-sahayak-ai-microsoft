"""
Protocol Engine - Rule-based triage evaluator.
Runs offline. No external dependencies required.
"""

import json
import os
from typing import Dict, Any

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")


def load_rules(path: str = RULES_PATH) -> list:
    with open(path, "r") as f:
        data = json.load(f)
    return data["conditions"]


def evaluate(symptoms: Dict[str, Any], rules_path: str = RULES_PATH) -> Dict[str, str]:
    """
    Evaluate symptoms against rules and return triage decision.

    Args:
        symptoms: dict with keys matching rule conditions
                  e.g. {"age_under_5": True, "fever": True, "fast_breathing": True}

    Returns:
        {"triage": "Urgent Referral", "matched_rule": "child_pneumonia_severe", "description": "..."}
    """
    conditions = load_rules(rules_path)

    for condition in conditions:
        rules = condition["rules"]
        if all(symptoms.get(key) == value for key, value in rules.items()):
            return {
                "triage": condition["triage"],
                "matched_rule": condition["id"],
                "description": condition["description"],
            }

    return {
        "triage": "Home Care",
        "matched_rule": "default",
        "description": "No matching condition found. Default to Home Care.",
    }


if __name__ == "__main__":
    # Quick smoke test
    test_cases = [
        {"age_under_5": True, "fever": True, "fast_breathing": True},
        {"age_under_5": True, "fever": True, "fast_breathing": False},
        {"age_under_5": False, "fever": True, "fast_breathing": False},
        {"age_under_5": False, "fever": False, "fast_breathing": False},
    ]
    for symptoms in test_cases:
        result = evaluate(symptoms)
        print(f"Symptoms: {symptoms}")
        print(f"  -> {result['triage']} ({result['matched_rule']})\n")
