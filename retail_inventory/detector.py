"""
YOLO-based product detection module.
=====================================
Loads a YOLOv8 model (custom best.pt preferred, pretrained yolov8l.pt fallback)
and exposes simple detect / draw helpers.

Key upgrades
------------
* ``set_allowed_classes(names)``  — runtime-configurable allowlist from the UI
* Pretrained COCO model: only shelf-relevant classes pass through by default
* Custom model: every class passes through (user trained on their products)
* Confidence threshold is applied at inference time (not cached globally)
"""

import os
import numpy as np
from typing import Dict, List, Optional, Set, Tuple

from utils import get_color_for_class

# ---------------------------------------------------------------------------
# Default COCO classes relevant to retail shelves.
# Used when a custom model is NOT loaded.
# ---------------------------------------------------------------------------
RETAIL_CLASSES: Set[str] = {
    # Drinks & containers
    "bottle", "wine glass", "cup",
    # Cutlery (retail aisle items)
    "fork", "knife", "spoon",
    # Food
    "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
    # Electronics / accessories
    "cell phone", "remote", "keyboard", "mouse", "laptop",
    # Household / stationery
    "book", "clock", "scissors", "toothbrush", "vase",
    "handbag", "backpack", "umbrella", "tie",
    "sports ball", "tennis racket",
}

# Classes to always exclude
EXCLUDED_CLASSES: Set[str] = {
    "person",
    # Animals
    "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe",
    # Vehicles
    "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat",
    # Large furniture / structures
    "traffic light", "fire hydrant", "stop sign", "parking meter",
    "bench", "bed", "dining table", "toilet", "couch",
    "tv", "oven", "microwave", "refrigerator", "sink",
}


class ProductDetector:
    """Wraps Ultralytics YOLOv8 for retail product detection."""

    def __init__(
        self,
        model_path: str = "best.pt",
        confidence: float = 0.5,
        allowed_classes: Optional[Set[str]] = None,
    ):
        """
        Args:
            model_path:      Path to a custom YOLO model.
                             Falls back to pretrained yolov8l.pt if not found.
            confidence:      Minimum detection confidence threshold.
            allowed_classes: If provided, only these class names pass through.
                             Overrides the default RETAIL_CLASSES filter.
                             Pass an empty set to allow all non-excluded classes.
        """
        self.confidence = confidence
        # User-defined allowlist (set via sidebar); None means "use defaults"
        self._allowed_classes: Optional[Set[str]] = allowed_classes
        self.model = None
        self.class_names: dict = {}
        self.using_custom_model: bool = False
        self._load_model(model_path)

    # -----------------------------------------------------------------------
    # Runtime configuration
    # -----------------------------------------------------------------------
    def set_confidence(self, confidence: float):
        """Update confidence threshold without reloading the model."""
        self.confidence = confidence

    def set_allowed_classes(self, names: Optional[Set[str]]):
        """
        Update the class allowlist at runtime (called from Streamlit sidebar).

        Pass ``None`` to revert to the default RETAIL_CLASSES filter.
        Pass an empty set to allow every non-excluded class.
        """
        self._allowed_classes = names

    def get_allowed_classes(self) -> Optional[Set[str]]:
        return self._allowed_classes

    # -----------------------------------------------------------------------
    # Model loading
    # -----------------------------------------------------------------------
    def _load_model(self, model_path: str):
        """Load YOLO model with graceful fallback."""
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError(
                "ultralytics is not installed. Run:  pip install ultralytics"
            )

        if os.path.exists(model_path):
            print(f"[detector] Loading custom model: {model_path}")
            self.model = YOLO(model_path)
            self.using_custom_model = True
        else:
            print("[detector] Custom model not found — loading pretrained yolov8l.pt")
            self.model = YOLO("yolov8l.pt")
            self.using_custom_model = False

        self.class_names = self.model.names  # {int: str}
        print(f"[detector] Ready — {len(self.class_names)} classes")
        if not self.using_custom_model:
            print("[detector] Retail filter active — only shelf/product objects kept")

    # -----------------------------------------------------------------------
    # Filtering logic
    # -----------------------------------------------------------------------
    def _is_allowed(self, class_name: str) -> bool:
        """
        Return True if this detection should be kept.

        Priority order:
        1. Always drop EXCLUDED_CLASSES (persons, animals, vehicles).
        2. If a user allowlist is set → only keep classes in that list.
        3. Custom model without allowlist → keep everything non-excluded.
        4. Pretrained COCO model without allowlist → keep RETAIL_CLASSES only.
        """
        # Rule 1: hard blacklist (applies to all models)
        if class_name in EXCLUDED_CLASSES:
            return False

        # Rule 2: user-defined allowlist overrides defaults
        if self._allowed_classes is not None:
            return class_name in self._allowed_classes

        # Rule 3 & 4: model-type defaults
        if self.using_custom_model:
            return True
        return class_name in RETAIL_CLASSES

    # -----------------------------------------------------------------------
    # Detection
    # -----------------------------------------------------------------------
    def detect(
        self, frame: np.ndarray
    ) -> Tuple[List[dict], Dict[str, int]]:
        """
        Run inference on a single BGR frame.

        Returns
        -------
        detections : list of dicts with keys 'class', 'confidence', 'bbox'
        counts     : {class_name: count}
        """
        if self.model is None:
            return [], {}

        results = self.model(frame, conf=self.confidence, verbose=False)

        detections: List[dict] = []
        counts: Dict[str, int] = {}

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                conf   = float(box.conf[0].item())
                name   = self.class_names[cls_id]

                # --- Apply allowlist / exclusion filter ---
                if not self._is_allowed(name):
                    continue

                coords = box.xyxy[0].cpu().numpy().tolist()
                detections.append({
                    "class":      name,
                    "confidence": conf,
                    "bbox":       coords,   # [x1, y1, x2, y2]
                })
                counts[name] = counts.get(name, 0) + 1

        return detections, counts

    def get_class_list(self) -> List[str]:
        """
        Return all class names the model can detect (post-filter).
        Used to populate the sidebar multiselect.
        """
        if isinstance(self.class_names, dict):
            all_names = list(self.class_names.values())
        else:
            all_names = list(self.class_names)

        # Apply same logic as _is_allowed (minus user allowlist override)
        if not self.using_custom_model:
            return sorted(n for n in all_names if n in RETAIL_CLASSES)
        return sorted(n for n in all_names if n not in EXCLUDED_CLASSES)
