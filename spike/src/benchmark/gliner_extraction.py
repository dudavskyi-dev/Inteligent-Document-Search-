from __future__ import annotations

import re
import time
from collections import defaultdict
from statistics import mean
from typing import Any


MODEL_NAME = "gliner-community/gliner_small-v2.5"
THRESHOLDS = (0.2, 0.3, 0.4, 0.5)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _find_occurrence(text: str, needle: str, occurrence: int) -> tuple[int, int]:
    start = -1
    search_from = 0
    for _ in range(occurrence + 1):
        start = text.find(needle, search_from)
        if start < 0:
            raise ValueError(
                f"Expected span {needle!r} occurrence {occurrence} is absent from {text!r}."
            )
        search_from = start + len(needle)
    return start, start + len(needle)


def prepare_cases(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    labels = dataset["labels"]
    if set(labels) != {"part_or_model", "quantity", "tolerance", "deadline", "price"}:
        raise ValueError("The extraction dataset must define exactly the five task labels.")

    seen: set[str] = set()
    prepared: list[dict[str, Any]] = []
    for source_case in dataset["cases"]:
        case = dict(source_case)
        case_id = case["case_id"]
        if case_id in seen:
            raise ValueError(f"Duplicate extraction case ID: {case_id}")
        seen.add(case_id)
        if case["source_kind"] not in {"real", "derived", "synthetic"}:
            raise ValueError(f"Unknown source_kind in {case_id}: {case['source_kind']}")

        expected: list[dict[str, Any]] = []
        for raw_entity in case["expected"]:
            entity = dict(raw_entity)
            label = entity["label"]
            if label not in labels:
                raise ValueError(f"Unknown label {label!r} in case {case_id}.")
            start, end = _find_occurrence(
                case["text"],
                entity["text"],
                int(entity.get("occurrence", 0)),
            )
            entity.update({"start": start, "end": end})
            expected.append(entity)
        case["expected"] = expected
        prepared.append(case)
    return prepared


def _deduplicate_predictions(
    predictions: list[dict[str, Any]],
    prompt_to_label: dict[str, str],
) -> list[dict[str, Any]]:
    best: dict[tuple[str, int, int], dict[str, Any]] = {}
    for prediction in predictions:
        prompt = str(prediction["label"]).casefold()
        if prompt not in prompt_to_label:
            continue
        item = {
            "text": str(prediction["text"]),
            "label": prompt_to_label[prompt],
            "start": int(prediction["start"]),
            "end": int(prediction["end"]),
            "score": float(prediction["score"]),
        }
        key = (item["label"], item["start"], item["end"])
        if key not in best or item["score"] > best[key]["score"]:
            best[key] = item
    return sorted(best.values(), key=lambda item: (item["start"], item["end"], item["label"]))


def predict_cases(
    model: Any,
    dataset: dict[str, Any],
    cases: list[dict[str, Any]],
    minimum_threshold: float,
) -> list[dict[str, Any]]:
    label_to_prompt = dataset["labels"]
    prompts = list(label_to_prompt.values())
    prompt_to_label = {prompt.casefold(): label for label, prompt in label_to_prompt.items()}
    results: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        raw = model.predict_entities(
            case["text"],
            prompts,
            threshold=minimum_threshold,
        )
        latency = time.perf_counter() - started
        results.append(
            {
                "case_id": case["case_id"],
                "source_kind": case["source_kind"],
                "source": case["source"],
                "page_number": case["page_number"],
                "evidence_id": case["evidence_id"],
                "text": case["text"],
                "expected": case["expected"],
                "latency_seconds": round(latency, 6),
                "predictions_at_minimum_threshold": _deduplicate_predictions(
                    raw, prompt_to_label
                ),
            }
        )
    return results


def _is_relaxed_match(expected: dict[str, Any], predicted: dict[str, Any]) -> bool:
    if expected["label"] != predicted["label"]:
        return False
    overlap = max(
        0,
        min(expected["end"], predicted["end"])
        - max(expected["start"], predicted["start"]),
    )
    if overlap <= 0:
        return False
    expected_text = _normalise(expected["text"])
    predicted_text = _normalise(predicted["text"])
    containment = expected_text in predicted_text or predicted_text in expected_text
    union_width = max(expected["end"], predicted["end"]) - min(
        expected["start"], predicted["start"]
    )
    return containment or overlap / union_width >= 0.5


def _match_counts(
    expected: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
    relaxed: bool,
) -> tuple[int, int, int, dict[str, dict[str, int]]]:
    unmatched = set(range(len(predicted)))
    true_positive = 0
    by_label: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0}
    )
    for entity in expected:
        matches: list[int] = []
        for index in unmatched:
            candidate = predicted[index]
            exact = (
                entity["label"] == candidate["label"]
                and entity["start"] == candidate["start"]
                and entity["end"] == candidate["end"]
            )
            if exact or (relaxed and _is_relaxed_match(entity, candidate)):
                matches.append(index)
        if matches:
            winner = max(matches, key=lambda index: predicted[index]["score"])
            unmatched.remove(winner)
            true_positive += 1
            by_label[entity["label"]]["tp"] += 1
        else:
            by_label[entity["label"]]["fn"] += 1
    for index in unmatched:
        by_label[predicted[index]["label"]]["fp"] += 1
    false_positive = len(unmatched)
    false_negative = len(expected) - true_positive
    return true_positive, false_positive, false_negative, by_label


def _scores(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _evaluate_subset(
    rows: list[dict[str, Any]],
    threshold: float,
    relaxed: bool,
) -> dict[str, Any]:
    totals = {"tp": 0, "fp": 0, "fn": 0}
    label_totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0}
    )
    case_f1: list[float] = []
    for row in rows:
        predictions = [
            item
            for item in row["predictions_at_minimum_threshold"]
            if item["score"] >= threshold
        ]
        tp, fp, fn, by_label = _match_counts(row["expected"], predictions, relaxed)
        totals["tp"] += tp
        totals["fp"] += fp
        totals["fn"] += fn
        case_f1.append(float(_scores(tp, fp, fn)["f1"]))
        for label, counts in by_label.items():
            for name in totals:
                label_totals[label][name] += counts[name]
    result = _scores(**totals)
    result["mean_case_f1"] = round(mean(case_f1), 6) if case_f1 else 0.0
    result["by_label"] = {
        label: _scores(**counts) for label, counts in sorted(label_totals.items())
    }
    return result


def evaluate_predictions(
    rows: list[dict[str, Any]],
    thresholds: tuple[float, ...] = THRESHOLDS,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    subsets = {
        "all": rows,
        "real": [row for row in rows if row["source_kind"] == "real"],
        "derived": [row for row in rows if row["source_kind"] == "derived"],
        "synthetic": [row for row in rows if row["source_kind"] == "synthetic"],
    }
    for threshold in thresholds:
        threshold_key = f"{threshold:.1f}"
        metrics[threshold_key] = {}
        for subset_name, subset_rows in subsets.items():
            metrics[threshold_key][subset_name] = {
                "case_count": len(subset_rows),
                "exact": _evaluate_subset(subset_rows, threshold, relaxed=False),
                "relaxed": _evaluate_subset(subset_rows, threshold, relaxed=True),
            }

    best_threshold = max(
        thresholds,
        key=lambda threshold: (
            metrics[f"{threshold:.1f}"]["real"]["relaxed"]["f1"],
            metrics[f"{threshold:.1f}"]["all"]["exact"]["f1"],
            metrics[f"{threshold:.1f}"]["real"]["relaxed"]["recall"],
            threshold,
        ),
    )
    best_key = f"{best_threshold:.1f}"
    best = metrics[best_key]
    label_recalls = [
        float(scores["recall"])
        for scores in best["all"]["relaxed"]["by_label"].values()
    ]
    quality_gate = {
        "real_relaxed_f1_required": 0.7,
        "all_exact_f1_required": 0.6,
        "minimum_relaxed_recall_per_label_required": 0.5,
        "real_relaxed_f1_passed": best["real"]["relaxed"]["f1"] >= 0.7,
        "all_exact_f1_passed": best["all"]["exact"]["f1"] >= 0.6,
        "per_label_recall_passed": bool(label_recalls) and min(label_recalls) >= 0.5,
    }
    quality_gate["passed"] = all(
        quality_gate[name]
        for name in (
            "real_relaxed_f1_passed",
            "all_exact_f1_passed",
            "per_label_recall_passed",
        )
    )
    return {
        "thresholds": metrics,
        "best_threshold_by_real_relaxed_f1": best_threshold,
        "quality_gate": quality_gate,
        "latency": {
            "mean_case_seconds": round(mean(row["latency_seconds"] for row in rows), 6),
            "max_case_seconds": round(max(row["latency_seconds"] for row in rows), 6),
            "total_inference_seconds": round(
                sum(row["latency_seconds"] for row in rows), 6
            ),
        },
    }
