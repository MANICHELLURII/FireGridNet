"""
Wraps YOLOv8 inference so routers stay thin.
Model is loaded once and cached; swap YOLO_MODEL_PATH in .env once you've
fine-tuned a fire/smoke checkpoint.
"""
import io
from functools import lru_cache

import numpy as np
from PIL import Image

from app.config import settings
from app.models.schemas import DetectionResult

# Class names your fine-tuned checkpoint should use, in this order.
FIRE_CLASS_NAMES = {0: "smoke", 1: "fire"}
MIN_DETECTION_CONFIDENCE = 0.4


@lru_cache
def get_model():
    from ultralytics import YOLO

    return YOLO(settings.yolo_model_path)


def run_detection(image_bytes: bytes, cell_id: str | None, source: str) -> DetectionResult:
    model = get_model()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    preds = model.predict(np.array(image), verbose=False)[0]

    fire_detected = False
    smoke_detected = False
    best_conf = 0.0
    best_bbox = None

    for box in preds.boxes:
        cls_id = int(box.cls.item())
        conf = float(box.conf.item())
        label = FIRE_CLASS_NAMES.get(cls_id, "unknown")

        if conf >= MIN_DETECTION_CONFIDENCE:
            if label == "fire":
                fire_detected = True
            elif label == "smoke":
                smoke_detected = True

        if conf > best_conf:
            best_conf = conf
            best_bbox = [float(x) for x in box.xyxy[0].tolist()]

    return DetectionResult(
        cell_id=cell_id,
        source=source,
        fire_detected=fire_detected,
        smoke_detected=smoke_detected,
        confidence=best_conf,
        bbox=best_bbox,
    )
