# AI Models

## Architecture

### AI Localization: UNet + EfficientNet-B3

| Property | Value |
|----------|-------|
| Architecture | UNet (segmentation-models-pytorch) |
| Encoder | EfficientNet-B3 |
| Input | 512×512 RGB |
| Output | 512×512 probability map [0,1] |
| Model name | `ai_localization_unet_efficientnet_b3` |
| Version | `v1.0.0` |

### Model Provenance (required per inference)

Every inference records:
- `model_name`
- `version`
- `weights_sha256` (hash of .pth file)
- `training_dataset` (ai_forensics_v1)
- `preprocessing_version` (v1)
- `threshold` (default: 0.50)
- `calibration_status` (UNCALIBRATED)

### Current Training Status

**No trained weights exist yet.** The model architecture is defined.
Training requires:
1. Collected and labelled dataset following `docs/DATASET.md`
2. Running the training script

```bash
python -m training.train_ai_detector \
  --dataset_dir ai_forensics/dataset \
  --output_dir training/output \
  --epochs 50 --batch_size 8 --img_size 512 \
  --backbone efficientnet-b3 --learning_rate 1e-4 --seed 42
```

### Training Outputs

| File | Description |
|------|-------------|
| `best_model.pth` | Best validation Dice checkpoint |
| `last_model.pth` | Final epoch checkpoint |
| `config.json` | Training configuration |
| `metrics.json` | Best and final metrics |
| `training_log.csv` | Per-epoch metrics |

### Setting Weights for Inference

```bash
export AI_WEIGHTS_PATH=training/output/best_model.pth
```

Or set in `.env`:
```env
AI_WEIGHTS_PATH=training/output/best_model.pth
```

### Calibration Status

All model outputs are **UNCALIBRATED**.
Raw sigmoid output is NOT a probability.
Calibration against a held-out calibration set is planned for Phase 9.

### Target Metrics (to be achieved after training)

| Metric | Target |
|--------|--------|
| Pixel F1 (2–5% edits) | TBD after training |
| IoU | TBD after training |
| ROC-AUC (image-level) | TBD after training |

These will be populated after the model is trained on a labelled dataset.
