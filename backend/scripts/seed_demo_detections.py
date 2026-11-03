"""Insert a small, explicitly labeled D-Fire test set into detections.

Run from ``backend/`` with the configured Supabase client and model available:
    python scripts/seed_demo_detections.py

This is a one-time demo seed. It fetches eight positive image records from the
D-Fire test split via the Hugging Face dataset viewer, runs the local FireGridNet
YOLO model directly, and inserts the model outputs as ``test_dataset`` rows.
These rows are evaluation data, not live field detections. Running this script
again inserts another set of rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(os.getenv("TEMP", ".")) / "firegridnet-yolo-config"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.services.detection_service import run_detection
from app.services.supabase_client import get_supabase

DATASET = "baizhanquan/FireDetectionDataset-flame-forest-flameye-wildfire"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE_SIZE = 100
MAX_SCAN_PAGES = 5


def get_positive_test_images(count: int) -> list[dict]:
    """Pick distinct images from rows explicitly tagged D-Fire/test/positive."""
    selected = []
    seen = set()
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for page in range(MAX_SCAN_PAGES):
            response = client.get(
                ROWS_URL,
                params={
                    "dataset": DATASET,
                    "config": "default",
                    "split": "test",
                    "offset": page * PAGE_SIZE,
                    "length": PAGE_SIZE,
                },
            )
            response.raise_for_status()
            rows = response.json().get("rows", [])
            for wrapped in rows:
                row = wrapped.get("row", {})
                image_id = row.get("image_id")
                image_url = (row.get("image") or {}).get("src")
                if (
                    row.get("source", "").lower() == "dfire"
                    and row.get("split") == "test"
                    and (row.get("has_fire") or row.get("has_smoke"))
                    and image_id not in seen
                    and image_url
                ):
                    selected.append({"image_id": image_id, "url": image_url})
                    seen.add(image_id)
                    if len(selected) >= count:
                        return selected
            if len(rows) < PAGE_SIZE:
                break
    raise RuntimeError(f"Found only {len(selected)} labeled positive D-Fire test images; need {count}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=8, choices=range(8, 11), metavar="{8,9,10}")
    args = parser.parse_args()

    samples = get_positive_test_images(args.count)
    sb = get_supabase()
    cells = sb.table("grid_cells").select("cell_id").order("cell_id").limit(2000).execute().data
    if len(cells) < args.count:
        raise RuntimeError(f"Only {len(cells)} grid cells are available; need {args.count}.")

    inserted = []
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for index, sample in enumerate(samples):
            image_response = client.get(sample["url"])
            image_response.raise_for_status()
            cell_id = cells[index]["cell_id"]
            result = run_detection(
                image_response.content,
                cell_id=cell_id,
                source="test_dataset",
            )
            payload = result.model_dump(mode="json", exclude_none=True)
            saved = sb.table("detections").insert(payload).execute().data[0]
            inserted.append({
                "id": saved["id"],
                "cell_id": saved["cell_id"],
                "confidence": saved["confidence"],
                "source": saved["source"],
                "fire_detected": saved["fire_detected"],
                "smoke_detected": saved["smoke_detected"],
                "image_id": sample["image_id"],
                "status": saved.get("status", "unavailable_until_status_migration"),
            })
            print(f"{index + 1}/{args.count}: {cell_id} {sample['image_id']} confidence={saved['confidence']:.4f}")

    print(json.dumps({"dataset": DATASET, "split": "test", "source_label": "test_dataset", "inserted": inserted}, indent=2))


if __name__ == "__main__":
    main()
