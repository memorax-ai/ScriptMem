#!/usr/bin/env python3
"""Export raw JSON files into public JSONL files."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Any


DATASET_FILES = ("angry.json", "enemy.json", "friends.json", "man_earth.json")


def dataset_name(filename: str) -> str:
    return filename[:-5]


def answer_letters(answer: Any) -> list[str]:
    parts = answer if isinstance(answer, list) else [answer]
    letters: list[str] = []
    for part in parts:
        match = re.match(r"\s*([A-F])\.", str(part))
        if match:
            letters.append(match.group(1))
    return letters


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(raw_dir: Path) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    total_questions = 0
    total_counter: collections.Counter[str] = collections.Counter()

    for filename in DATASET_FILES:
        source = dataset_name(filename)
        path = raw_dir / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        qas = [qa for sample in data for qa in sample.get("qa", [])]
        by_type = collections.Counter(qa.get("qa_type", "") for qa in qas)
        total_questions += len(qas)
        total_counter.update(by_type)
        datasets[source] = {
            "file": f"data/raw/{filename}",
            "question_count": len(qas),
            "qa_type_counts": {
                "multi_select": by_type["multi_select"],
                "ordering": by_type["ordering"],
                "single_choice": by_type["single_choice"],
            },
            "sha256": sha256(path),
        }

    return {
        "dataset_name": "scriptmem",
        "dataset_file_name": "data/raw/*.json",
        "conversation_count": len(DATASET_FILES),
        "question_count": total_questions,
        "qa_type_counts": {
            "multi_select": total_counter["multi_select"],
            "ordering": total_counter["ordering"],
            "single_choice": total_counter["single_choice"],
        },
        "files": {
            "raw": "data/raw",
            "conversations": "data/public/conversations.jsonl",
            "questions": "data/public/questions.jsonl",
            "submission_template": "data/public/submission_template.json",
        },
        "datasets": datasets,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/raw", help="Directory containing raw JSON files.")
    parser.add_argument("--out-dir", default="data/public", help="Output directory for JSONL files.")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conversations: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    submission_template: list[dict[str, Any]] = []

    for filename in DATASET_FILES:
        source = dataset_name(filename)
        data = json.loads((raw_dir / filename).read_text(encoding="utf-8"))
        for sample_index, sample in enumerate(data):
            sample_id = sample.get("sample_id") or f"{source}-{sample_index}"
            conversation_id = f"{source}:{sample_id}"
            conversations.append(
                {
                    "conversation_id": conversation_id,
                    "source": source,
                    "sample_id": sample_id,
                    "conversation": sample["conversation"],
                }
            )

            for qa_index, qa in enumerate(sample.get("qa", [])):
                qa_id = f"{source}:{sample_id}#q{qa_index:04d}"
                question_id = qa_id
                question_row = {
                    "qa_id": qa_id,
                    "question_id": question_id,
                    "conversation_id": conversation_id,
                    "source": source,
                    "sample_id": sample_id,
                    "qa_index": qa_index,
                    "qa_type": qa["qa_type"],
                    "question": qa["question"],
                    "option": qa["option"],
                    "answer": qa["answer"],
                    "answer_letters": answer_letters(qa["answer"]),
                }
                questions.append(question_row)
                while len(submission_template) <= list(DATASET_FILES).index(filename):
                    submission_template.append({"dataset": source, "qa_results": []})
                submission_template[-1]["qa_results"].append({"qa_id": qa_id, "predicted_answer": ""})

    write_jsonl(out_dir / "conversations.jsonl", conversations)
    write_jsonl(out_dir / "questions.jsonl", questions)
    (out_dir / "submission_template.json").write_text(
        json.dumps(submission_template, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest = build_manifest(raw_dir)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "conversations": len(conversations),
                "questions": len(questions),
                "submission_template_groups": len(submission_template),
                "submission_template_items": sum(len(item["qa_results"]) for item in submission_template),
                "manifest": str(out_dir / "manifest.json"),
                "out_dir": str(out_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
