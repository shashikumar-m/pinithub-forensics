"""
Dataset Splitter & Frozen Test Set — Phase 9A.

Creates a reproducible source-level split and freezes the test set.
NO source-image leakage: all variants of the same source stay in one split.

The frozen test manifest (splits/frozen_test.json) is SEALED at creation.
Once frozen, training code MUST NOT read from it.
Only the final evaluation script is allowed to use the frozen test.

Split: 70% train | 15% validation | 15% test
Fixed seed: 42
"""
from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from app.models.ai_dataset import ManifestEntry, AIForensicsManifest, split_dataset

DATASET_VERSION = "ai_forensics_v1"
SPLIT_SEED = 42


@dataclass
class FrozenTestManifest:
    """Immutable record of the frozen test set."""
    dataset_version: str
    creation_timestamp: str
    seed: int
    source_image_ids: list
    image_ids: list
    entry_count: int
    manifest_sha256: str          # SHA-256 of the serialized entries
    label_counts: dict = field(default_factory=dict)
    area_bucket_counts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def create_splits(
    entries: list[ManifestEntry],
    dataset_dir: str,
    seed: int = SPLIT_SEED,
) -> tuple[list[ManifestEntry], list[ManifestEntry], list[ManifestEntry]]:
    """
    Create train/val/test splits with source-image isolation.
    Writes manifests and creates the frozen test file.
    Returns (train, val, test).
    """
    train, val, test = split_dataset(entries, seed=seed)
    manifest = AIForensicsManifest(dataset_dir)
    manifest.write(train, "train")
    manifest.write(val, "val")
    manifest.write(test, "test")
    freeze_test_set(test, dataset_dir)
    return train, val, test


def freeze_test_set(
    test_entries: list[ManifestEntry],
    dataset_dir: str,
) -> FrozenTestManifest:
    """
    Create a frozen test manifest.
    Once written, this file should never be overwritten.
    """
    splits_dir = Path(dataset_dir) / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = splits_dir / "frozen_test.json"

    # Compute SHA-256 of the serialized entry list for integrity
    entry_json = json.dumps(
        [e.to_dict() for e in test_entries],
        sort_keys=True, separators=(",", ":")
    )
    manifest_sha256 = hashlib.sha256(entry_json.encode()).hexdigest()

    source_ids = list({e.source_image or e.image for e in test_entries})
    image_ids = [e.image for e in test_entries]

    label_counts: dict = {}
    bucket_counts: dict = {}
    for e in test_entries:
        label_counts[e.label] = label_counts.get(e.label, 0) + 1
        if e.area_bucket:
            bucket_counts[e.area_bucket] = bucket_counts.get(e.area_bucket, 0) + 1

    frozen = FrozenTestManifest(
        dataset_version=DATASET_VERSION,
        creation_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        seed=SPLIT_SEED,
        source_image_ids=sorted(source_ids),
        image_ids=sorted(image_ids),
        entry_count=len(test_entries),
        manifest_sha256=manifest_sha256,
        label_counts=label_counts,
        area_bucket_counts=bucket_counts,
    )

    with open(frozen_path, "w", encoding="utf-8") as f:
        json.dump(frozen.to_dict(), f, indent=2)

    return frozen


def load_frozen_test(dataset_dir: str) -> Optional[FrozenTestManifest]:
    """Load the frozen test manifest if it exists."""
    frozen_path = Path(dataset_dir) / "splits" / "frozen_test.json"
    if not frozen_path.exists():
        return None
    with open(frozen_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return FrozenTestManifest(**d)


def validate_no_leakage(
    train: list[ManifestEntry],
    val: list[ManifestEntry],
    test: list[ManifestEntry],
) -> list[str]:
    """
    Check for source-image leakage between any two splits.
    Returns a list of violation messages (empty = clean).
    """
    def sources(entries):
        return {e.source_image or e.image for e in entries}

    train_s = sources(train)
    val_s = sources(val)
    test_s = sources(test)

    violations = []
    tv = train_s & val_s
    tt = train_s & test_s
    vt = val_s & test_s

    if tv:
        violations.append(f"TRAIN/VAL leakage: {sorted(tv)[:5]}... ({len(tv)} sources)")
    if tt:
        violations.append(f"TRAIN/TEST leakage: {sorted(tt)[:5]}... ({len(tt)} sources)")
    if vt:
        violations.append(f"VAL/TEST leakage: {sorted(vt)[:5]}... ({len(vt)} sources)")

    return violations


def check_test_not_in_train(
    train: list[ManifestEntry],
    frozen: FrozenTestManifest,
) -> list[str]:
    """
    Verify that none of the frozen test source images appear in training data.
    """
    test_sources = set(frozen.source_image_ids)
    train_sources = {e.source_image or e.image for e in train}
    overlap = test_sources & train_sources
    if overlap:
        return [f"FROZEN TEST appears in TRAIN: {sorted(overlap)[:5]}..."]
    return []
