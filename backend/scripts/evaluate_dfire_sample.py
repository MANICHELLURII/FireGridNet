"""Image-level YOLO evaluation on a deterministic, stratified D-Fire test sample.

Run from ``backend/``:
    python scripts/evaluate_dfire_sample.py --per-class 4

Downloads only the selected images from the public dataset viewer. This is a
small sample check, not a full D-Fire benchmark or box-localization mAP test.
Results are saved under backend/reports/ and never written to Supabase.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(os.getenv("TEMP", ".")) / "firegridnet-yolo-config"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import settings
from app.services.detection_service import get_model, run_detection

DATASET = "baizhanquan/FireDetectionDataset-flame-forest-flameye-wildfire"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
CATEGORIES = ("none", "fire_only", "smoke_only", "fire_and_smoke")


def category_for(fire: bool, smoke: bool) -> str:
    if fire and smoke:
        return "fire_and_smoke"
    if fire:
        return "fire_only"
    if smoke:
        return "smoke_only"
    return "none"


def collect_stratified_samples(client: httpx.Client, per_class: int, max_pages: int) -> list[dict]:
    selected = {category: [] for category in CATEGORIES}
    for page in range(max_pages):
        response = client.get(
            ROWS_URL,
            params={"dataset": DATASET, "config": "default", "split": "test", "offset": page * 100, "length": 100},
        )
        response.raise_for_status()
        rows = response.json().get("rows", [])
        for wrapped in rows:
            row = wrapped.get("row", {})
            if row.get("source", "").lower() != "dfire" or row.get("split") != "test":
                continue
            category = category_for(bool(row.get("has_fire")), bool(row.get("has_smoke")))
            if len(selected[category]) < per_class and row.get("image", {}).get("src"):
                selected[category].append({
                    "image_id": row.get("image_id"),
                    "url": row["image"]["src"],
                    "ground_truth": category,
                    "has_fire": bool(row.get("has_fire")),
                    "has_smoke": bool(row.get("has_smoke")),
                })
        if all(len(selected[category]) >= per_class for category in CATEGORIES):
            break
        if len(rows) < 100:
            break

    missing = {category: per_class - len(selected[category]) for category in CATEGORIES if len(selected[category]) < per_class}
    if missing:
        raise RuntimeError(f"Not enough D-Fire test rows in the requested strata: {missing}")
    return [item for category in CATEGORIES for item in selected[category][:per_class]]


def binary_metrics(rows: list[dict], truth_key: str, prediction_key: str) -> dict:
    tp = sum(bool(row[truth_key]) and bool(row[prediction_key]) for row in rows)
    fp = sum(not bool(row[truth_key]) and bool(row[prediction_key]) for row in rows)
    fn = sum(bool(row[truth_key]) and not bool(row[prediction_key]) for row in rows)
    tn = len(rows) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and precision + recall else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall, "f1": f1}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=4, help="Images sampled from each of the four dataset categories.")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum dataset-viewer pages to scan.")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "reports")
    args = parser.parse_args()
    if args.per_class < 1 or args.max_pages < 1:
        parser.error("--per-class and --max-pages must be positive")

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        samples = collect_stratified_samples(client, args.per_class, args.max_pages)
        get_model.cache_clear()
        details = []
        for sample in samples:
            image_response = client.get(sample["url"])
            image_response.raise_for_status()
            started = time.perf_counter()
            result = run_detection(image_response.content, cell_id=None, source="evaluation")
            elapsed_ms = (time.perf_counter() - started) * 1000
            predicted = category_for(result.fire_detected, result.smoke_detected)
            details.append({
                "image_id": sample["image_id"],
                "ground_truth": sample["ground_truth"],
                "predicted": predicted,
                "ground_truth_fire": sample["has_fire"],
                "ground_truth_smoke": sample["has_smoke"],
                "fire_detected": result.fire_detected,
                "smoke_detected": result.smoke_detected,
                "confidence": round(result.confidence, 6),
                "inference_ms": round(elapsed_ms, 3),
            })

    confusion = {truth: {prediction: 0 for prediction in CATEGORIES} for truth in CATEGORIES}
    for row in details:
        confusion[row["ground_truth"]][row["predicted"]] += 1
    correct = sum(row["ground_truth"] == row["predicted"] for row in details)
    report = {
        "evaluation": "dfire_image_level_sample",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": DATASET,
        "split": "test",
        "dataset_source_filter": "dfire",
        "sample_size": len(details),
        "sample_per_category": args.per_class,
        "metric_scope": "Image-level fire/smoke flags; no bounding-box localization metric (mAP) is computed.",
        "model_path": str(Path(settings.yolo_model_path).resolve()),
        "class_names": get_model().names,
        "overall_image_category_accuracy": correct / len(details) if details else None,
        "overall_correct": correct,
        "overall_total": len(details),
        "fire_binary_metrics": binary_metrics(details, "ground_truth_fire", "fire_detected"),
        "smoke_binary_metrics": binary_metrics(details, "ground_truth_smoke", "smoke_detected"),
        "confusion_matrix": confusion,
        "images": details,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "model_accuracy_latest.json"
    csv_path = args.output_dir / "model_accuracy_images_latest.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=details[0].keys())
        writer.writeheader()
        writer.writerows(details)
    print(json.dumps({key: value for key, value in report.items() if key != "images"}, indent=2))
    print(f"JSON summary written to: {json_path.resolve()}")
    print(f"Per-image CSV written to: {csv_path.resolve()}")


if __name__ == "__main__":
    main()
