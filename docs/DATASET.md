# AI Forensics Dataset

## Structure

```
ai_forensics/
├── real/                    # Real camera photographs (authentic)
├── ai_generated/            # Fully AI-generated images
├── ai_edited/               # Real photos with localized AI edits
│   ├── object_removal/
│   ├── generative_fill/
│   ├── object_insertion/
│   ├── background_edit/
│   └── retouching/
├── masks/                   # Ground-truth binary masks
└── manifests/
    ├── train.jsonl
    ├── val.jsonl
    └── test.jsonl
```

## Manifest Format (JSON Lines)

```json
{
  "image": "ai_edited/generative_fill/img_001.jpg",
  "source_image": "real/img_001.jpg",
  "label": "AI_EDITED_LOCAL",
  "edit_type": "generative_fill",
  "mask": "masks/generative_fill/img_001_mask.png",
  "edited_area_percentage": 5.4,
  "generator": "stable_diffusion_2_inpainting",
  "split": "train",
  "postprocessing": null,
  "dataset_version": "ai_forensics_v1"
}
```

## Labels
- `REAL` — unedited original photograph
- `AI_GENERATED` — fully AI-generated image
- `AI_EDITED_LOCAL` — real photograph with localized AI edit + mask

## Split Strategy

70% train / 15% validation / 15% test

**Source-image leakage prevention:** All versions derived from the same source photograph must be in the same split. The `source_image` field is used as the grouping key.

**Test set is FROZEN.** Thresholds must never be tuned using the test set.

## Edit Area Buckets (mandatory reporting)

| Bucket | Range |
|--------|-------|
| `<0.5%` | Very small edits |
| `0.5–1%` | Small edits |
| `1–2%` | Small-medium (**key target for 2% requirement**) |
| `2–5%` | Medium-small |
| `5–10%` | Medium |
| `10–25%` | Large |
| `>25%` | Very large |

## Post-Processing Robustness Suite

Evaluation variants created for each test image:
- JPEG q=95, q=85, q=75, q=60
- Resize 75%, Resize 50%
- Screenshot (PNG)
- Crop + resize
- Brightness +20%
- Contrast +30%
- Mild sharpening

## Dataset Generation & Splitting Scripts (Phase 1)

The pipeline provides complete automation for generating and partitioning evaluation datasets per Section 6.2 and 6.3 of `PinITHUB_Plan.pdf`:

### 1. Dataset Generation
```bash
python -m datasets.generate --output-dir data/forensics_v1 --n-sources 20 --seed 42
```
Generates all 10 edit families:
1. `generative_fill` (diffusion-like latent pattern insertion with feathered boundary)
2. `generative_inpaint` (object removal with plausible texture synthesis)
3. `splicing` (patch insertion from distinct donor image)
4. `copy_move` (spatial clone of region with affine displacement)
5. `retouching` (bilateral smoothing and skin-tone adjustment)
6. `text_insertion` (synthetic high-frequency text overlays)
7. `crop` (perimetral border crop and resampling)
8. `perspective_warp` (projective geometric skew)
9. `color_grading` (localized hue and saturation LUT adjustments)
10. `recompression_pipeline` (double JPEG recompression with 8x8 DCT grid misalignment)

Across all 7 Area Buckets:
`<0.5%`, `0.5–1%`, `1–2%`, `2–5%`, `5–10%`, `10–25%`, `>25%`

And post-processing suites:
- JPEG Q95, Q85, Q75, Q60
- Resize 0.5x, 0.75x, 1.25x
- WhatsApp pipeline (recompress Q75 + resize max 1600px)
- Instagram pipeline (recompress Q80 + square crop / resize max 1080px)
- Lossless PNG

### 2. Zero-Leakage Grouped Splitting & Freezing
```bash
python -m datasets.splits --manifest data/forensics_v1/manifest.json --output-dir data/forensics_v1 --seed 42
```
- Partitions 70% train / 15% val / 15% test strictly grouped by `source_image`.
- Asserts zero leakage (`set.intersection` of source IDs across splits is empty).
- Holds out `flux_1_schnell` exclusively in the test split for unseen-tool evaluation.
- Freezes test set with deterministic SHA-256 manifest hash stored in `test_frozen_manifest.json`.

## Current Status

- Fully operational scripts implemented in `services/forensics/datasets/generate.py` and `services/forensics/datasets/splits.py`.
- Automated test coverage in `services/forensics/tests/test_phase9a.py` and `services/forensics/tests/test_ai_detection.py`.
