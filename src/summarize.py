#!/usr/bin/env python3
"""CLI and helpers for summarizing ScriptMem evaluation results."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_json_or_jsonl(path: str | Path) -> Any:
    source = Path(path)
    if source.suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return records
    return json.loads(source.read_text(encoding="utf-8"))


def load_and_summarize_scores(input_path: str | Path) -> dict[str, Any]:
    payload = load_json_or_jsonl(input_path)
    if isinstance(payload, list):
        return summarize_score_records(payload)
    if isinstance(payload, dict):
        details = payload.get("details")
        if isinstance(details, list):
            return summarize_score_records(details)
        return normalize_summary(payload)
    raise ValueError("input must be a JSON object, JSON list, or JSONL file")


def summarize_score_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [item for item in records if isinstance(item, dict)]
    by_dataset: dict[str, Counter[str]] = defaultdict(Counter)
    by_qa_type: dict[str, Counter[str]] = defaultdict(Counter)
    by_dataset_and_qa_type: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    overall: Counter[str] = Counter()

    for item in normalized:
        dataset = str(item.get("dataset") or item.get("source") or "unknown")
        qa_type = str(item.get("qa_type") or "unknown")
        score = float(item.get("score") or 0.0)
        missing = bool(item.get("missing_prediction"))
        malformed = bool(item.get("malformed_prediction"))
        for counter in (overall, by_dataset[dataset], by_qa_type[qa_type], by_dataset_and_qa_type[dataset][qa_type]):
            update_counter(counter, score=score, missing=missing, malformed=malformed)

    return {
        "primary_metric": "accuracy",
        "record_count": int(overall["count"]),
        "overall": counter_summary(overall),
        "by_dataset": {key: counter_summary(value) for key, value in sorted(by_dataset.items())},
        "by_qa_type": {key: counter_summary(value) for key, value in sorted(by_qa_type.items())},
        "by_dataset_and_qa_type": {
            dataset: {qa_type: counter_summary(counter) for qa_type, counter in sorted(groups.items())}
            for dataset, groups in sorted(by_dataset_and_qa_type.items())
        },
    }


def normalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    normalized.setdefault("primary_metric", "accuracy")
    normalized.setdefault("record_count", int(normalized.get("count", 0) or 0))
    if "overall" not in normalized:
        normalized["overall"] = {
            "count": int(normalized.get("count", 0) or 0),
            "score": float(normalized.get("score", 0.0) or 0.0),
            "accuracy": float(normalized.get("accuracy", 0.0) or 0.0),
            "missing_prediction_count": int(normalized.get("missing_prediction_count", 0) or 0),
            "malformed_prediction_count": int(normalized.get("malformed_prediction_count", 0) or 0),
        }
    return normalized


def update_counter(counter: Counter[str], *, score: float, missing: bool, malformed: bool) -> None:
    counter["count"] += 1
    counter["score"] += score
    if missing:
        counter["missing_prediction_count"] += 1
    if malformed:
        counter["malformed_prediction_count"] += 1


def counter_summary(counter: Counter[str]) -> dict[str, Any]:
    count = int(counter["count"])
    score = float(counter["score"])
    return {
        "count": count,
        "score": score,
        "accuracy": score / count if count else 0.0,
        "missing_prediction_count": int(counter["missing_prediction_count"]),
        "malformed_prediction_count": int(counter["malformed_prediction_count"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize ScriptMem evaluation details or summary JSON")
    parser.add_argument("--input-path", required=True, help="Path to eval details JSON, eval summary JSON, or scored JSONL.")
    parser.add_argument("--output-path", default=None, help="Path for summary JSON.")
    parser.add_argument("--markdown-output-path", default=None, help="Path for Markdown summary.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output_path = Path(args.output_path) if args.output_path else default_output_path(args.input_path)
    markdown_output_path = (
        Path(args.markdown_output_path) if args.markdown_output_path else default_markdown_output_path(output_path)
    )
    summary = load_and_summarize_scores(args.input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output_path.write_text(render_score_markdown(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "output_path": str(output_path),
                "markdown_output_path": str(markdown_output_path),
                "primary_metric": summary.get("primary_metric", "accuracy"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def default_output_path(input_path: str | Path) -> Path:
    path = Path(input_path)
    return path.with_name(f"{path.stem}_summary.json")


def default_markdown_output_path(output_path: str | Path) -> Path:
    return Path(output_path).with_suffix(".md")


def render_score_markdown(summary: dict[str, Any]) -> str:
    sections: list[str] = ["# ScriptMem Score Summary", ""]
    overall = summary.get("overall")
    if isinstance(overall, dict):
        sections.append("## Overall")
        sections.append("")
        sections.extend(render_summary_table({"overall": overall}, "Group"))
        sections.append("")

    by_dataset = summary.get("by_dataset")
    if isinstance(by_dataset, dict) and by_dataset:
        sections.append("## By Dataset")
        sections.append("")
        sections.extend(render_summary_table(by_dataset, "Dataset"))
        sections.append("")

    by_qa_type = summary.get("by_qa_type")
    if isinstance(by_qa_type, dict) and by_qa_type:
        sections.append("## By QA Type")
        sections.append("")
        sections.extend(render_summary_table(by_qa_type, "QA Type"))
        sections.append("")

    matrix = summary.get("by_dataset_and_qa_type")
    if isinstance(matrix, dict) and matrix:
        sections.append("## Dataset x QA Type")
        sections.append("")
        sections.extend(render_matrix_table(matrix))
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def render_summary_table(groups: dict[str, Any], group_header: str) -> list[str]:
    lines = [
        f"| {group_header} | Count | Score | Accuracy | Missing | Malformed |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, payload in sorted(groups.items()):
        if not isinstance(payload, dict):
            continue
        lines.append(
            "| {name} | {count} | {score} | {accuracy} | {missing} | {malformed} |".format(
                name=key,
                count=int(payload.get("count", 0) or 0),
                score=format_number(payload.get("score")),
                accuracy=format_percent(payload.get("accuracy")),
                missing=int(payload.get("missing_prediction_count", 0) or 0),
                malformed=int(payload.get("malformed_prediction_count", 0) or 0),
            )
        )
    return lines


def render_matrix_table(matrix: dict[str, Any]) -> list[str]:
    qa_types = sorted({qa_type for groups in matrix.values() if isinstance(groups, dict) for qa_type in groups})
    lines = [
        "| Dataset | " + " | ".join(qa_types) + " |",
        "| --- | " + " | ".join(["---:"] * len(qa_types)) + " |",
    ]
    for dataset, groups in sorted(matrix.items()):
        row = [dataset]
        for qa_type in qa_types:
            payload = groups.get(qa_type) if isinstance(groups, dict) else None
            row.append(format_percent(payload.get("accuracy")) if isinstance(payload, dict) else "-")
        lines.append("| " + " | ".join(row) + " |")
    return lines


def format_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}"


def format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


if __name__ == "__main__":
    main()
