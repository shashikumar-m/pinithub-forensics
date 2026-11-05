"""
AI Forensics Training Script — Phase 6.

Trains UNet + EfficientNet-B3 for AI-edit localization.

Usage:
    python -m training.train_ai_detector \\
        --dataset_dir ai_forensics/dataset \\
        --output_dir training/output \\
        --epochs 50 \\
        --batch_size 8 \\
        --img_size 512 \\
        --backbone efficientnet-b3 \\
        --learning_rate 1e-4 \\
        --seed 42

Supports GPU (CUDA) when available. Falls back to CPU.

Logs:
  training_log.csv    — per-epoch metrics
  config.json         — training configuration
  metrics.json        — final best/last metrics

Saves:
  best_model.pth      — best validation Dice/F1
  last_model.pth      — final checkpoint
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from PIL import Image as PILImage

# These imports require the installed packages
try:
    import segmentation_models_pytorch as smp
    import albumentations as A
    from albumentations.pytorch import ToTensorV2
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

from app.models.ai_dataset import AIForensicsManifest, ManifestEntry, AREA_BUCKETS


# ---- Dataset ----

class AIForensicsDataset(Dataset):
    """PyTorch dataset for AI forensics segmentation."""

    def __init__(
        self,
        entries: list[ManifestEntry],
        dataset_dir: str,
        img_size: tuple = (512, 512),
        augment: bool = False,
    ):
        self.entries = entries
        self.dataset_dir = Path(dataset_dir)
        self.img_size = img_size
        self.augment = augment

        if augment:
            self.transform = A.Compose([
                A.HorizontalFlip(p=0.5),
                A.RandomBrightnessContrast(p=0.3),
                A.GaussNoise(p=0.2),
                A.RandomRotate90(p=0.3),
                A.Resize(*img_size),
                A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ToTensorV2(),
            ])
        else:
            self.transform = A.Compose([
                A.Resize(*img_size),
                A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                ToTensorV2(),
            ])

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> dict:
        entry = self.entries[idx]
        img_path = self.dataset_dir / entry.image

        # Load image
        img = np.array(PILImage.open(img_path).convert("RGB"), dtype=np.uint8)

        # Load mask
        if entry.mask:
            mask_path = self.dataset_dir / entry.mask
            mask = np.array(PILImage.open(mask_path).convert("L"), dtype=np.float32)
            mask = (mask > 127).astype(np.float32)
        elif entry.label == "AI_GENERATED":
            mask = np.ones((img.shape[0], img.shape[1]), dtype=np.float32)
        else:
            mask = np.zeros((img.shape[0], img.shape[1]), dtype=np.float32)

        # Apply transforms
        transformed = self.transform(image=img, mask=mask)
        return {
            "image": transformed["image"],
            "mask": transformed["mask"].unsqueeze(0),
            "label": entry.label,
            "path": str(img_path),
        }


# ---- Metrics ----

def compute_metrics(preds: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> dict:
    """Compute pixel-level segmentation metrics."""
    preds_bin = (torch.sigmoid(preds) > threshold).float()
    targets = targets.float()

    tp = (preds_bin * targets).sum().item()
    fp = (preds_bin * (1 - targets)).sum().item()
    fn = ((1 - preds_bin) * targets).sum().item()
    tn = ((1 - preds_bin) * (1 - targets)).sum().item()

    eps = 1e-7
    precision = tp / (tp + fp + eps)
    recall = tp / (tp + fn + eps)
    f1 = 2 * precision * recall / (precision + recall + eps)
    iou = tp / (tp + fp + fn + eps)
    dice = 2 * tp / (2 * tp + fp + fn + eps)

    return {
        "pixel_precision": round(precision, 4),
        "pixel_recall": round(recall, 4),
        "pixel_f1": round(f1, 4),
        "iou": round(iou, 4),
        "dice": round(dice, 4),
    }


# ---- Training loop ----

def train(args: argparse.Namespace) -> None:
    if not _DEPS_AVAILABLE:
        print("ERROR: segmentation-models-pytorch and albumentations required for training")
        print("Install: pip install segmentation-models-pytorch albumentations")
        sys.exit(1)

    # Seed for reproducibility
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load manifests
    manifest = AIForensicsManifest(args.dataset_dir)
    splits = manifest.load_all()

    print(f"Train: {len(splits['train'])} | Val: {len(splits['val'])} | Test: {len(splits['test'])}")

    if len(splits["train"]) == 0:
        print("ERROR: No training data found. Check dataset_dir and manifests/train.jsonl")
        sys.exit(1)

    # Check for leakage
    all_entries = splits["train"] + splits["val"] + splits["test"]
    violations = manifest.validate_split_isolation(all_entries)
    if violations:
        print("WARNING: Source-image leakage detected!")
        for v in violations:
            print(f"  {v}")

    img_size = (args.img_size, args.img_size)
    train_ds = AIForensicsDataset(splits["train"], args.dataset_dir, img_size, augment=True)
    val_ds = AIForensicsDataset(splits["val"], args.dataset_dir, img_size, augment=False)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                               num_workers=0, pin_memory=False)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False,
                             num_workers=0)

    # Build model
    model = smp.Unet(
        encoder_name=args.backbone,
        encoder_weights="imagenet",
        in_channels=3,
        classes=1,
        activation=None,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
    criterion = smp.losses.DiceLoss(mode="binary")
    bce = nn.BCEWithLogitsLoss()

    # Save config
    config = {
        "model_name": "ai_localization_unet_efficientnet_b3",
        "version": "v1.0.0",
        "backbone": args.backbone,
        "img_size": args.img_size,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "seed": args.seed,
        "device": str(device),
        "dataset_dir": args.dataset_dir,
        "training_samples": len(splits["train"]),
        "val_samples": len(splits["val"]),
    }
    with open(output_dir / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    # Training loop
    best_dice = 0.0
    best_metrics: dict = {}
    log_path = output_dir / "training_log.csv"

    with open(log_path, "w", newline="") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(["epoch", "train_loss", "val_loss", "val_f1",
                          "val_iou", "val_dice", "val_precision", "val_recall", "lr", "epoch_secs"])

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        model.train()
        train_loss = 0.0

        for batch in train_loader:
            imgs = batch["image"].to(device)
            masks = batch["mask"].to(device)
            optimizer.zero_grad()
            logits = model(imgs)
            loss = criterion(logits, masks) + 0.5 * bce(logits, masks)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= max(1, len(train_loader))

        # Validation
        model.eval()
        val_loss = 0.0
        all_preds, all_masks = [], []

        with torch.no_grad():
            for batch in val_loader:
                imgs = batch["image"].to(device)
                masks = batch["mask"].to(device)
                logits = model(imgs)
                loss = criterion(logits, masks) + 0.5 * bce(logits, masks)
                val_loss += loss.item()
                all_preds.append(logits.cpu())
                all_masks.append(masks.cpu())

        val_loss /= max(1, len(val_loader))
        preds_cat = torch.cat(all_preds)
        masks_cat = torch.cat(all_masks)
        metrics = compute_metrics(preds_cat, masks_cat)

        scheduler.step(val_loss)
        lr = optimizer.param_groups[0]["lr"]
        epoch_secs = time.time() - t0

        print(
            f"Epoch {epoch:3d}/{args.epochs} | "
            f"train={train_loss:.4f} val={val_loss:.4f} | "
            f"F1={metrics['pixel_f1']:.4f} IoU={metrics['iou']:.4f} "
            f"Dice={metrics['dice']:.4f} | lr={lr:.2e} | {epoch_secs:.1f}s"
        )

        with open(log_path, "a", newline="") as csvf:
            writer = csv.writer(csvf)
            writer.writerow([epoch, f"{train_loss:.4f}", f"{val_loss:.4f}",
                              metrics["pixel_f1"], metrics["iou"], metrics["dice"],
                              metrics["pixel_precision"], metrics["pixel_recall"],
                              f"{lr:.2e}", f"{epoch_secs:.1f}"])

        # Save best model
        if metrics["dice"] > best_dice:
            best_dice = metrics["dice"]
            best_metrics = {**metrics, "epoch": epoch, "val_loss": val_loss}
            torch.save(model.state_dict(), output_dir / "best_model.pth")

    # Save last model
    torch.save(model.state_dict(), output_dir / "last_model.pth")

    final_metrics = {
        "best_val_metrics": best_metrics,
        "last_epoch": args.epochs,
        "model_name": "ai_localization_unet_efficientnet_b3",
        "version": "v1.0.0",
    }
    with open(output_dir / "metrics.json", "w") as f:
        json.dump(final_metrics, f, indent=2)

    print(f"\nTraining complete. Best Dice: {best_dice:.4f}")
    print(f"Saved to: {output_dir}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train AI forensics detector")
    parser.add_argument("--dataset_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--img_size", type=int, default=512)
    parser.add_argument("--backbone", default="efficientnet-b3")
    parser.add_argument("--learning_rate", type=float, default=1e-4)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
