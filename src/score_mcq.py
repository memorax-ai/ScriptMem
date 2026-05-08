#!/usr/bin/env python3
"""Deterministic scorer for ScriptMem multiple-choice predictions."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ANSWER_RE = re.compile(r"^\s*([A-F])\.")


def load_qa(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    qas: list[dict[str, Any]] = []
    for sample in data:
        qas.extend(sample["qa"])
    return qas


def load_predictions(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        raw_items = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        raw_items = json.loads(text)
    predictions: list[str] = []
    for item in raw_items:
        if isinstance(item, str):
            predictions.append(item)
        elif isinstance(item, dict):
            for key in ("predicted_answer", "prediction", "answer", "response"):
                if key in item:
                    predictions.append(str(item[key]))
                    break
            else:
                predictions.append("")
        else:
            predictions.append(str(item))
    return predictions


def gold_letters(answer: Any) -> list[str]:
    parts = answer if isinstance(answer, list) else [answer]
    letters: list[str] = []
    for part in parts:
        match = ANSWER_RE.match(str(part))
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
    if not letters:
        return [], False
    return letters, len(set(letters)) != len(letters)


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


def score_item(qa_type: str, gold: list[str], pred: list[str], malformed: bool = False) -> float:
    if malformed:
        return 0.0
    if qa_type == "single_choice":
        return 1.0 if len(gold) == 1 and len(pred) == 1 and gold[0] == pred[0] else 0.0
    if qa_type == "multi_select":
        return 1.0 if bool(gold) and set(gold) == set(pred) and len(pred) == len(set(pred)) else 0.0
    if qa_type == "ordering":
        return 1.0 if bool(gold) and gold == pred else 0.0
    raise ValueError(f"unsupported qa_type: {qa_type}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_json", help="Dataset file such as angry.json.")
    parser.add_argument("predictions", help="JSON or JSONL predictions in dataset order.")
    parser.add_argument("--details", help="Optional path for per-item scoring details.")
    args = parser.parse_args()

    qas = load_qa(Path(args.dataset_json))
    predictions = load_predictions(Path(args.predictions))
    if len(qas) != len(predictions):
        raise SystemExit(f"Prediction count mismatch: expected {len(qas)}, got {len(predictions)}")

    details: list[dict[str, Any]] = []
    total = 0.0
    for index, (qa, prediction) in enumerate(zip(qas, predictions), start=1):
        gold = gold_letters(qa["answer"])
        pred, malformed = predicted_letters(prediction, qa["qa_type"])
        item_score = score_item(qa["qa_type"], gold, pred, malformed)
        total += item_score
        details.append(
            {
                "index": index,
                "qa_type": qa["qa_type"],
                "gold": gold,
                "predicted": pred,
                "score": item_score,
                "malformed_prediction": malformed,
            }
        )

    if args.details:
        Path(args.details).write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")

    count = len(qas)
    print(json.dumps({"count": count, "total": total, "accuracy": total / count if count else 0.0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
