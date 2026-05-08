#!/usr/bin/env python3
"""Official evaluator for ScriptMem submissions.

The expected submission format is a JSON list with four dictionaries, one per
dataset:

[
  {
    "dataset": "angry",
    "qa_results": [
      {"qa_id": "angry:conv-0#q0000", "predicted_answer": "(B)"}
    ]
  }
]

The evaluator also accepts common aliases such as ``prediction`` / ``response``
for ``predicted_answer``.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DATASET_FILES = ("angry.json", "enemy.json", "friends.json", "man_earth.json")
PREDICTION_FIELDS = ("predicted_answer", "prediction", "answer", "response")


def dataset_name(filename: str) -> str:
    return filename[:-5]


def load_gold_records(data_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for filename in DATASET_FILES:
        source = dataset_name(filename)
        path = data_dir / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        for sample_index, sample in enumerate(data):
            sample_id = sample.get("sample_id") or f"{source}-{sample_index}"
            for qa_index, qa in enumerate(sample.get("qa", [])):
                qa_id = f"{source}:{sample_id}#q{qa_index:04d}"
                records.append(
                    {
                        "qa_id": qa_id,
                        "dataset": source,
                        "sample_id": sample_id,
                        "qa_index": qa_index,
                        "qa_type": qa["qa_type"],
                        "question": qa["question"],
                        "answer": qa["answer"],
                    }
                )
    return records


def load_submission(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    predictions: dict[str, str] = {}

    def prediction_text(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for field in PREDICTION_FIELDS:
                if field in item:
                    return str(item.get(field) or "")
        return ""

    def add_result(item: Any, *, dataset: str | None = None, index: int | None = None) -> None:
        if isinstance(item, dict):
            qa_id = item.get("qa_id") or item.get("question_id")
            if not qa_id and dataset is not None and index is not None:
                qa_id = f"{dataset}:conv-0#q{index:04d}"
            if qa_id:
                predictions[str(qa_id)] = prediction_text(item)
        elif dataset is not None and index is not None:
            predictions[f"{dataset}:conv-0#q{index:04d}"] = prediction_text(item)

    if isinstance(payload, list):
        for group in payload:
            if not isinstance(group, dict):
                continue
            dataset = str(group.get("dataset") or group.get("source") or group.get("corpus") or "")
            results = (
                group.get("qa_results")
                or group.get("results")
                or group.get("predictions")
                or group.get("answers")
                or []
            )
            if isinstance(results, list):
                for index, item in enumerate(results):
                    add_result(item, dataset=dataset or None, index=index)
    elif isinstance(payload, dict):
        for dataset, value in payload.items():
            results = value
            if isinstance(value, dict):
                results = (
                    value.get("qa_results")
                    or value.get("results")
                    or value.get("predictions")
                    or value.get("answers")
                    or []
                )
            if isinstance(results, list):
                for index, item in enumerate(results):
                    add_result(item, dataset=str(dataset), index=index)
    else:
        raise ValueError("submission must be a JSON list or object")

    return predictions


def gold_letters(answer: Any) -> list[str]:
    parts = answer if isinstance(answer, list) else [answer]
    letters: list[str] = []
    for part in parts:
        match = re.match(r"\s*([A-F])\.", str(part))
        if match:
            letters.append(match.group(1))
    return letters


def normalize_prediction_text(text: str) -> str:
    cleaned = str(text or "").strip()
    box_matches = list(re.finditer(r"\\box(?:ed)?\{([^}]*)(?:\}|$)", cleaned))
    if box_matches:
        return box_matches[-1].group(1).strip()
    lower = cleaned.lower()
    if "final answer:" in lower:
        index = lower.index("final answer:")
        cleaned = cleaned[index + len("final answer:") :].strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1].strip()
    return cleaned


def predicted_letters(prediction: str, qa_type: str = "") -> tuple[list[str], bool]:
    normalized = normalize_prediction_text(prediction)
    if not normalized:
        return [], False

    if qa_type in {"multi_select", "ordering"}:
        return predicted_ordered_letters(normalized)

    return predicted_option_letters(normalized)


def predicted_ordered_letters(prediction: str) -> tuple[list[str], bool]:
    paren_matches = list(re.finditer(r"[\(\[]([^)\]]*)[\)\]]", prediction))
    content = paren_matches[-1].group(1) if paren_matches else prediction
    letters = [letter.upper() for letter in re.findall(r"[A-Fa-f]", content)]
    if letters:
        return letters, len(set(letters)) != len(letters)
    return [], False


def predicted_option_letters(prediction: str) -> tuple[list[str], bool]:
    if re.fullmatch(r"[A-Fa-f]{1,5}", prediction):
        return [letter.upper() for letter in prediction], False
    if re.search(r"\(\s*[A-Fa-f]\s*\)\(\s*[A-Fa-f]\s*\)", prediction) or re.search(
        r"\[\s*[A-Fa-f]\s*\]\[\s*[A-Fa-f]\s*\]",
        prediction,
    ):
        return [], True

    options: set[str] = set()
    token_re = re.compile(r"\([^)]*\)|\[[^\]]*\]")
    for match in token_re.finditer(prediction):
        inner = match.group(0)[1:-1].strip()
        if not inner:
            continue

        single_letter_match = re.fullmatch(r"([A-Fa-f])", inner)
        if single_letter_match:
            options.add(single_letter_match.group(1).upper())
            continue

        labeled_text_match = re.match(r"^([A-Fa-f])\s*[.:]\s*.+$", inner)
        if labeled_text_match:
            options.add(labeled_text_match.group(1).upper())
            continue

        letters_only = re.sub(r"[^A-Za-z]", "", inner)
        if (
            letters_only
            and len(letters_only) <= 5
            and inner[0].upper() in {"A", "B", "C", "D", "E", "F"}
            and re.fullmatch(r"[A-Za-z ]+", inner)
        ):
            options.add(inner[0].upper())
    return sorted(options), False


def score_item(qa_type: str, gold: list[str], pred: list[str], malformed: bool) -> float:
    if malformed:
        return 0.0
    if qa_type == "single_choice":
        return 1.0 if len(gold) == 1 and len(pred) == 1 and gold[0] == pred[0] else 0.0
    if qa_type == "multi_select":
        return 1.0 if bool(gold) and set(gold) == set(pred) and len(pred) == len(set(pred)) else 0.0
    if qa_type == "ordering":
        return 1.0 if bool(gold) and gold == pred else 0.0
    raise ValueError(f"unsupported qa_type: {qa_type}")


def evaluate(data_dir: Path, submission_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    gold_records = load_gold_records(data_dir)
    predictions = load_submission(submission_path)
    details: list[dict[str, Any]] = []
    by_dataset: dict[str, Counter[str]] = defaultdict(Counter)
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    missing_predictions: list[str] = []

    for record in gold_records:
        qa_id = record["qa_id"]
        prediction = predictions.get(qa_id, "")
        if qa_id not in predictions:
            missing_predictions.append(qa_id)
        gold = gold_letters(record["answer"])
        pred, malformed = predicted_letters(prediction, record["qa_type"])
        item_score = score_item(record["qa_type"], gold, pred, malformed)
        dataset_counter = by_dataset[record["dataset"]]
        type_counter = by_type[record["qa_type"]]
        for counter in (dataset_counter, type_counter):
            counter["count"] += 1
            counter["score"] += item_score
        details.append(
            {
                "qa_id": qa_id,
                "dataset": record["dataset"],
                "qa_index": record["qa_index"],
                "qa_type": record["qa_type"],
                "gold": gold,
                "predicted": pred,
                "score": item_score,
                "missing_prediction": qa_id not in predictions,
                "malformed_prediction": malformed,
            }
        )

    total_count = len(gold_records)
    total_score = sum(item["score"] for item in details)
    extra_predictions = sorted(set(predictions) - {record["qa_id"] for record in gold_records})

    summary = {
        "count": total_count,
        "score": total_score,
        "accuracy": total_score / total_count if total_count else 0.0,
        "missing_prediction_count": len(missing_predictions),
        "extra_prediction_count": len(extra_predictions),
        "by_dataset": {
            key: {
                "count": int(value["count"]),
                "score": float(value["score"]),
                "accuracy": float(value["score"]) / int(value["count"]) if value["count"] else 0.0,
            }
            for key, value in sorted(by_dataset.items())
        },
        "by_qa_type": {
            key: {
                "count": int(value["count"]),
                "score": float(value["score"]),
                "accuracy": float(value["score"]) / int(value["count"]) if value["count"] else 0.0,
            }
            for key, value in sorted(by_type.items())
        },
    }
    if missing_predictions:
        summary["missing_prediction_examples"] = missing_predictions[:20]
    if extra_predictions:
        summary["extra_prediction_examples"] = extra_predictions[:20]
    return summary, details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data/raw", help="Directory containing angry/enemy/friends/man_earth JSON files.")
    parser.add_argument("--submission", required=True, help="Submission JSON file.")
    parser.add_argument("--output", help="Optional path for the summary JSON.")
    parser.add_argument("--details", help="Optional path for per-question details JSON.")
    args = parser.parse_args()

    summary, details = evaluate(Path(args.data_dir), Path(args.submission))
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.details:
        details_path = Path(args.details)
        details_path.parent.mkdir(parents=True, exist_ok=True)
        details_path.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
