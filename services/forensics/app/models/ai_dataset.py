"""
AI Forensics Dataset — Phase 6.

Handles manifest loading, source-image split isolation, and PyTorch Dataset
classes for AI-generated and AI-edited image forensics.

Source-image leakage prevention:
  If multiple edited versions share the same source_image, all must stay
  in the same split. GroupShuffleSplit is used to enforce this.

Edit area buckets (mandatory per Phase 6 spec):
  <0.5% | 0.5–1% | 1–2% | 2–5% | 5–10% | 10–25% | >25%
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image as PILImage

# Bucket boundaries for edit-area percentage reporting
AREA_BUCKETS = [
    (0.0, 0.5, "<0.5%"),
    (0.5, 1.0, "0.5–1%"),
    (1.0, 2.0, "1–2%"),
    (2.0, 5.0, "2–5%"),
    (5.0, 10.0, "5–10%"),
    (10.0, 25.0, "10–25%"),
    (25.0, 101.0, ">25%"),
]

VALID_LABELS = {"REAL", "AI_GENERATED", "AI_EDITED_LOCAL"}
VALID_EDIT_TYPES = {
    "object_removal", "generative_fill", "object_insertion",
    "background_edit", "retouching",
}


def assign_area_bucket(pct: Optional[float]) -> str:
    """Helper to return area bucket string from area percentage."""
    if pct is None:
        return "NONE"
    for lo, hi, name in AREA_BUCKETS:
        if lo <= pct < hi:
            return name
    return ">25%"


@dataclass
class ManifestEntry:
    """A single entry in the AI forensics dataset manifest."""
    image: str                   # relative path to image file
    label: str                   # REAL | AI_GENERATED | AI_EDITED_LOCAL
    split: str                   # train | val | test
    source_image: Optional[str] = None    # for ai_edited: source photograph
    edit_type: Optional[str] = None       # for ai_edited
    mask: Optional[str] = None            # relative path to binary mask
    edited_area_percentage: Optional[float] = None
    generator: Optional[str] = None       # AI model used
    postprocessing: Optional[dict] = None
    dataset_version: str = "ai_forensics_v1"

    @property
    def area_bucket(self) -> Optional[str]:
        if self.edited_area_percentage is None:
            return None
        for lo, hi, name in AREA_BUCKETS:
            if lo <= self.edited_area_percentage < hi:
                return name
        return ">25%"

    def validate(self) -> list[str]:
        errors = []
        if self.label not in VALID_LABELS:
            errors.append(f"Invalid label: {self.label}")
        if self.label == "AI_EDITED_LOCAL":
            if not self.mask:
                errors.append("AI_EDITED_LOCAL entry must have a mask")
            if not self.edit_type:
                errors.append("AI_EDITED_LOCAL entry must have an edit_type")
            if self.edit_type and self.edit_type not in VALID_EDIT_TYPES:
                errors.append(f"Unknown edit_type: {self.edit_type}")
        return errors

    def to_dict(self) -> dict:
        return {
            "image": self.image,
            "label": self.label,
            "split": self.split,
            "source_image": self.source_image,
            "edit_type": self.edit_type,
            "mask": self.mask,
            "edited_area_percentage": self.edited_area_percentage,
            "generator": self.generator,
            "postprocessing": self.postprocessing,
            "dataset_version": self.dataset_version,
        }


class AIForensicsManifest:
    """Loads and manages the AI forensics dataset manifests."""

    def __init__(self, dataset_dir: str):
        self.dataset_dir = Path(dataset_dir)
        self._entries: list[ManifestEntry] = []

    def load(self, split: str) -> list[ManifestEntry]:
        """Load a split manifest (train/val/test)."""
        manifest_path = self.dataset_dir / "manifests" / f"{split}.jsonl"
        if not manifest_path.exists():
            return []
        entries = []
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entry = ManifestEntry(**{k: v for k, v in data.items()
                                         if k in ManifestEntry.__dataclass_fields__})
                entries.append(entry)
        return entries

    def load_all(self) -> dict[str, list[ManifestEntry]]:
        return {
            "train": self.load("train"),
            "val": self.load("val"),
            "test": self.load("test"),
        }

    def validate_split_isolation(self, entries: list[ManifestEntry]) -> list[str]:
        """
        Verify that source images do not appear in multiple splits.
        Returns a list of leakage violations.
        """
        source_to_splits: dict[str, set[str]] = {}
        for e in entries:
            if e.source_image:
                if e.source_image not in source_to_splits:
                    source_to_splits[e.source_image] = set()
                source_to_splits[e.source_image].add(e.split)

        violations = []
        for src, splits in source_to_splits.items():
            if len(splits) > 1:
                violations.append(
                    f"Source image leakage: {src} appears in splits: {splits}"
                )
        return violations

    def write(self, entries: list[ManifestEntry], split: str) -> None:
        """Write entries to a split manifest."""
        manifest_dir = self.dataset_dir / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        path = manifest_dir / f"{split}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e.to_dict()) + "\n")

    def statistics(self, entries: list[ManifestEntry]) -> dict:
        """Compute dataset statistics."""
        total = len(entries)
        by_label = {}
        by_edit_type = {}
        by_bucket = {}

        for e in entries:
            by_label[e.label] = by_label.get(e.label, 0) + 1
            if e.edit_type:
                by_edit_type[e.edit_type] = by_edit_type.get(e.edit_type, 0) + 1
            if e.area_bucket:
                by_bucket[e.area_bucket] = by_bucket.get(e.area_bucket, 0) + 1

        return {
            "total": total,
            "by_label": by_label,
            "by_edit_type": by_edit_type,
            "by_area_bucket": by_bucket,
        }


def split_dataset(
    entries: list[ManifestEntry],
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    seed: int = 42,
) -> tuple[list[ManifestEntry], list[ManifestEntry], list[ManifestEntry]]:
    """
    Split entries respecting source-image isolation.
    All entries sharing the same source_image end up in the same split.
    """
    from sklearn.model_selection import GroupShuffleSplit

    # Group by source_image (or image path for entries without source)
    groups = [e.source_image or e.image for e in entries]
    unique_groups = list(set(groups))
    random.seed(seed)
    random.shuffle(unique_groups)

    n = len(unique_groups)
    n_val = max(1, int(n * val_frac))
    n_test = max(1, int(n * val_frac))
    n_train = n - n_val - n_test

    train_groups = set(unique_groups[:n_train])
    val_groups = set(unique_groups[n_train:n_train + n_val])
    test_groups = set(unique_groups[n_train + n_val:])

    train, val, test = [], [], []
    for e in entries:
        g = e.source_image or e.image
        if g in train_groups:
            e.split = "train"
            train.append(e)
        elif g in val_groups:
            e.split = "val"
            val.append(e)
        else:
            e.split = "test"
            test.append(e)

    return train, val, test
