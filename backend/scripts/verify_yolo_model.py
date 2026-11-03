"""Load a YOLO checkpoint and print its class names and detections for an image.

Run from the repository root or backend directory:
    python backend/scripts/verify_yolo_model.py path/to/image.jpg
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

# Keep Ultralytics' first-run settings write in the system temp directory rather
# than requiring a user-profile write when running in a restricted environment.
os.environ.setdefault("YOLO_CONFIG_DIR", str(Path(os.getenv("TEMP", ".")) / "firegridnet-yolo-config"))

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Image file to run inference on")
    parser.add_argument(
        "--model",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "app" / "ml_models" / "yolov8n_fire.pt",
        help="YOLO .pt checkpoint (defaults to the backend fire model)",
    )
    parser.add_argument("--confidence", type=float, default=0.25)
    args = parser.parse_args()

    if not args.model.is_file():
        parser.error(f"model checkpoint not found: {args.model}")
    if not args.image.is_file():
        parser.error(f"image not found: {args.image}")

    model = YOLO(str(args.model))
    results = model.predict(source=str(args.image), conf=args.confidence, verbose=False)
    result = results[0]

    names = model.names
    detections = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        detections.append(
            {
                "class_id": class_id,
                "class_name": names.get(class_id, str(class_id))
                if isinstance(names, dict)
                else names[class_id],
                "confidence": float(box.conf.item()),
                "bbox_xyxy": [float(value) for value in box.xyxy[0].tolist()],
            }
        )

    print(json.dumps({"model": str(args.model.resolve()),
                      "image": str(args.image.resolve()),
                      "class_names": names,
                      "detection_count": len(detections),
                      "detections": detections}, indent=2))


if __name__ == "__main__":
    main()
