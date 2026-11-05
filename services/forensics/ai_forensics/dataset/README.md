# AI Forensics Dataset

## Structure

```
ai_forensics/
├── real/                    # Real camera photographs (authentic, unedited)
├── ai_generated/            # Fully AI-generated images
├── ai_edited/               # Real photos with localized AI edits
│   ├── object_removal/      # AI object removal (e.g. generative fill removing objects)
│   ├── generative_fill/     # Generative fill / inpainting
│   ├── object_insertion/    # AI-inserted objects
│   ├── background_edit/     # Background replacement / generation
│   └── retouching/          # AI face/body retouching
├── masks/                   # Ground-truth binary masks for ai_edited images
│   └── {edit_type}/         # Organized by edit type (mirrors ai_edited/)
└── manifests/               # Dataset manifests (JSON Lines)
    ├── train.jsonl
    ├── val.jsonl
    └── test.jsonl
```

## Manifest Format

Each line in the manifest is a JSON object:

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
  "postprocessing": null
}
```

Labels:
- `REAL` — unedited original photograph
- `AI_GENERATED` — fully AI-generated image
- `AI_EDITED_LOCAL` — real photograph with localized AI edit

## Source-Image Leakage Prevention

ALL versions of the same source image MUST be in the same split.
Use source_image path as the grouping key for stratified splitting.

## Split Strategy

70% train / 15% validation / 15% test

The test split is FROZEN. Thresholds must not be tuned on the test set.

## Important

This directory is in .gitignore. Dataset images and masks are NOT committed.
Only manifests and this README describe the structure.
