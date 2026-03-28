"""
Protocol Engine - Enhanced rule-based triage evaluator.
Supports both simple boolean matching (rules.json) and weighted scoring (protocols.json).
Runs offline. No external dependencies required.
"""

import json
import os
from typing import Dict, Any

PROTOCOLS_PATH = os.path.join(os.path.dirname(__file__), "protocols.json")
RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")


def load_protocols(path: str = PROTOCOLS_PATH) -> list:
    with open(path, "r") as f:
        data = json.load(f)
    return data["conditions"]


def load_rules(path: str = RULES_PATH) -> list:
    with open(path, "r") as f:
        data = json.load(f)
    return data["conditions"]


def evaluate(symptoms: Dict[str, Any], protocols_path: str = PROTOCOLS_PATH) -> Dict[str, Any]:
    """
    Enhanced evaluation with weighted scoring and confidence.

    Algorithm:
      1. Filter conditions by patient age and pregnancy status
      2. For each condition: calculate weighted score from matching triggers
      3. Apply risk modifiers from patient history flags
      4. Compare score against thresholds → triage tier
      5. confidence = rawScore / maxPossibleScore
      6. Return the most severe matching result
    """
    if not os.path.exists(protocols_path):
        return evaluate_simple(symptoms)

    conditions = load_protocols(protocols_path)
    best_result = None
    best_severity = -1

    for cond in conditions:
        # Age filter: patient_age_max_months > 0 means child-only
        age_max = cond.get("patient_age_max_months", 0)
        if age_max > 0 and not symptoms.get("age_under_5", False):
            continue

        # Pregnancy filter
        if cond.get("requires_pregnant", False) and not symptoms.get("pregnant", False):
            continue

        # Calculate weighted score
        triggers = cond.get("triggers", [])
        raw_score = 0.0
        max_possible = 0.0
        has_all_required = True

        for trigger in triggers:
            symptom = trigger["symptom"]
            weight = trigger["weight"]
            required = trigger.get("required", False)

            max_possible += weight

            if symptoms.get(symptom, False):
                raw_score += weight
            elif required:
                has_all_required = False

        if not has_all_required or raw_score == 0:
            continue

        # Apply risk modifiers
        adjusted_score = raw_score
        for mod in cond.get("risk_modifiers", []) or []:
            if symptoms.get(mod["flag"], False):
                adjusted_score *= mod["multiplier"]

        # Determine triage from thresholds
        thresholds = cond.get("thresholds", {})
        urgent_t = thresholds.get("urgent_referral", 999)
        phc_t = thresholds.get("phc_visit", 999)

        if adjusted_score >= urgent_t:
            triage = "Urgent Referral"
            severity = 2
        elif adjusted_score >= phc_t:
            triage = "PHC Visit"
            severity = 1
        else:
            triage = "Home Care"
            severity = 0

        confidence = min(raw_score / max_possible, 1.0) if max_possible > 0 else 0.0

        if severity > best_severity or (
            severity == best_severity
            and confidence > (best_result or {}).get("confidence", 0)
        ):
            best_severity = severity
            # Collect applicable follow-up questions for low confidence
            follow_ups = []
            if confidence < 0.70:
                for fq in cond.get("follow_up_questions", []):
                    trigger = fq.get("trigger_symptom", "")
                    if trigger and not symptoms.get(trigger, False):
                        continue
                    follow_ups.append(fq)

            best_result = {
                "triage": triage,
                "matched_rule": cond["id"],
                "description": cond.get("rationale", ""),
                "confidence": round(confidence, 2),
                "score": round(adjusted_score, 2),
                "max_score": round(max_possible, 2),
                "follow_up_questions": follow_ups,
            }

    return best_result or {
        "triage": "Home Care",
        "matched_rule": "default",
        "description": "No matching condition found. Default to Home Care.",
        "confidence": 0.0,
        "score": 0.0,
        "max_score": 0.0,
        "follow_up_questions": [],
    }


def evaluate_simple(symptoms: Dict[str, Any], rules_path: str = RULES_PATH) -> Dict[str, Any]:
    """Backward-compatible simple boolean matching using rules.json."""
    conditions = load_rules(rules_path)
    for condition in conditions:
        rules = condition["rules"]
        if all(symptoms.get(key) == value for key, value in rules.items()):
            return {
                "triage": condition["triage"],
                "matched_rule": condition["id"],
                "description": condition["description"],
                "confidence": 1.0,
                "score": 0.0,
                "max_score": 0.0,
            }
    return {
        "triage": "Home Care",
        "matched_rule": "default",
        "description": "No matching condition found. Default to Home Care.",
        "confidence": 0.0,
        "score": 0.0,
        "max_score": 0.0,
    }


if __name__ == "__main__":
    print("=== Enhanced Protocol Evaluation (Weighted Scoring) ===\n")
    test_cases = [
        {"age_under_5": True, "fever": True, "fast_breathing": True},
        {"age_under_5": True, "fever": True, "fast_breathing": True, "chest_indrawing": True},
        {"age_under_5": True, "diarrhea": True, "vomiting": True},
        {"age_under_5": True, "convulsions": True},
        {"age_under_5": True, "fever": True, "fast_breathing": False},
        {"fever": True, "severe_headache": True, "vomiting": True},
        {"pregnant": True, "vaginal_bleeding": True},
        {"pregnant": True, "severe_headache": True},
        {"fever": True},
        {},
    ]
    for symptoms in test_cases:
        result = evaluate(symptoms)
        conf_pct = int(result["confidence"] * 100)
        uncertain = " -- UNCERTAIN" if result["confidence"] < 0.70 else ""
        print(f"Symptoms: {symptoms}")
        print(f"  -> {result['triage']} ({result['matched_rule']}) — Confidence: {conf_pct}%{uncertain}")
        print(f"     Score: {result['score']}/{result['max_score']}")
        print()
