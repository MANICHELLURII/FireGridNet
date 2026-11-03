"""Benchmark FireGridNet's YOLO inference path on real local images.

Examples (from backend/):
    python scripts/evaluate_execution.py
    python scripts/evaluate_execution.py --images-dir data/dfire/test/images --iterations 5
    python scripts/evaluate_execution.py --image scripts/sample_fire.png --iterations 20

This measures execution performance only. It does not claim accuracy metrics,
and it does not insert benchmark results into Supabase.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
import platform
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(os.getenv("TEMP", ".")) / "firegridnet-yolo-config"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services.detection_service import get_model, run_detection

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def collect_images(image_args: list[Path], image_dir: Path | None, default_image: Path) -> list[Path]:
    candidates = list(image_args)
    if image_dir:
        if not image_dir.is_dir():
            raise ValueError(f"Image directory does not exist: {image_dir}")
        candidates.extend(path for path in image_dir.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS)
    if not candidates:
        candidates = [default_image]
    missing = [str(path) for path in candidates if not path.is_file()]
    if missing:
        raise ValueError("Image file(s) not found: " + ", ".join(missing))
    return sorted(dict.fromkeys(path.resolve() for path in candidates))


def synchronize_accelerator() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except ImportError:
        pass


def benchmark(images: list[Path], iterations: int, warmup: int) -> dict:
    image_bytes = {path: path.read_bytes() for path in images}
    first_path = images[0]

    # Clear the process-local model cache so this first timing includes model
    # initialization plus its first real prediction (cold start).
    get_model.cache_clear()
    synchronize_accelerator()
    started = time.perf_counter()
    first_result = run_detection(image_bytes[first_path], cell_id=None, source="benchmark")
    synchronize_accelerator()
    cold_start_ms = (time.perf_counter() - started) * 1000

    for index in range(warmup):
        path = images[(index + 1) % len(images)]
        run_detection(image_bytes[path], cell_id=None, source="benchmark")

    samples = []
    for run_index in range(iterations):
        for image_index, path in enumerate(images):
            synchronize_accelerator()
            started = time.perf_counter()
            result = run_detection(image_bytes[path], cell_id=None, source="benchmark")
            synchronize_accelerator()
            elapsed_ms = (time.perf_counter() - started) * 1000
            samples.append({
                "run": run_index + 1,
                "image": path.name,
                "latency_ms": round(elapsed_ms, 3),
                "confidence": round(result.confidence, 6),
                "fire_detected": result.fire_detected,
                "smoke_detected": result.smoke_detected,
            })

    latencies = [row["latency_ms"] for row in samples]
    elapsed_seconds = sum(latencies) / 1000
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "unknown"

    model = get_model()
    return {
        "evaluation": "yolo_inference_execution_performance",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "run_detection() with image bytes preloaded; includes image decoding and model inference, excludes Supabase/network I/O",
        "model_path": str(Path(settings.yolo_model_path).resolve()),
        "model_class_names": model.names,
        "device": device,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "image_count": len(images),
        "images": [path.name for path in images],
        "warmup_runs": warmup,
        "iterations_per_image": iterations,
        "measured_inferences": len(samples),
        "cold_start_first_inference_ms": round(cold_start_ms, 3),
        "warm_latency_ms": {
            "min": round(min(latencies), 3),
            "mean": round(statistics.fmean(latencies), 3),
            "median": round(statistics.median(latencies), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "max": round(max(latencies), 3),
        },
        "throughput_images_per_second": round(len(samples) / elapsed_seconds, 3) if elapsed_seconds else None,
        "cold_first_image_result": {
            "confidence": round(first_result.confidence, 6),
            "fire_detected": first_result.fire_detected,
            "smoke_detected": first_result.smoke_detected,
        },
        "runs": samples,
    }


def write_reports(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "execution_latest.json"
    csv_path = output_dir / "execution_runs_latest.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    columns = ("run", "image", "latency_ms", "confidence", "fire_detected", "smoke_detected")
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(report["runs"])
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", type=Path, default=[], help="Image to include (repeatable).")
    parser.add_argument("--images-dir", type=Path, help="Recursively benchmark supported images in this directory.")
    parser.add_argument("--iterations", type=int, default=10, help="Measured passes per image after warm-up.")
    parser.add_argument("--warmup", type=int, default=2, help="Unmeasured warm-up inference calls.")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "reports", help="Output folder for JSON summary and per-run CSV.")
    args = parser.parse_args()
    if args.iterations < 1 or args.warmup < 0:
        parser.error("--iterations must be >= 1 and --warmup must be >= 0")

    default_image = Path(__file__).resolve().parent / "sample_fire.png"
    images = collect_images(args.image, args.images_dir, default_image)
    report = benchmark(images, args.iterations, args.warmup)
    json_path, csv_path = write_reports(report, args.output_dir)
    summary = {key: value for key, value in report.items() if key != "runs"}
    print(json.dumps(summary, indent=2))
    print(f"JSON summary written to: {json_path.resolve()}")
    print(f"Per-inference CSV written to: {csv_path.resolve()}")


if __name__ == "__main__":
    main()
