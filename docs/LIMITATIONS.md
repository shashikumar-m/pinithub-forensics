# Limitations

This document explicitly states all known limitations of the PinITHUB Forensics system.

## Core Principles

- No forensic detector produces a guaranteed result.
- "NOT_EDITED" does not mean "guaranteed authentic".
- "EDITED" does not identify the editor or prove intent.
- All detector scores are UNCALIBRATED unless explicitly stated otherwise.

---

## AI Detection (Phase 6 / Phase 9A)

- **Experimental.** AI detection is not independently validated.
- **UNCALIBRATED.** Raw sigmoid output is not a probability.
- **No trained weights.** Until a labelled dataset is collected and training completes, all AI detection returns `UNAVAILABLE`. The system correctly returns `UNAVAILABLE` (not `NO_AI_EVIDENCE`) — the distinction is enforced and tested.
- **Synthetic dataset only.** The current frozen test set uses synthetic images. Real-world performance is unknown.
- **Frozen test set established.** SHA-256: `501b9c4be656eb28689f51622a851b04...`. No leakage detected between splits.
- **No pixel-level metrics available.** Pixel F1, IoU, Dice, MCC all require trained weights.
- **2% edit detectability unknown** until model is trained and evaluated on real data.
- **Unseen generators.** Detection accuracy on AI models not seen during training is unknown.
- **Compression destroys signal.** Heavy JPEG compression can reduce AI-edit evidence.

## Classical Forensic Signals (Phase 3)

- Classical signals (ELA, noise residual, DCT, copy-move) are not individually definitive.
- ELA is sensitive to the original JPEG quality level.
- Resampling detector can produce false positives on images with natural periodic structures.
- Copy-move detector is conservative — may miss smooth or small duplicated regions.
- JPEG double-compression evidence is not proof of manipulation intent.

## Metadata (Phase 2)

- Metadata is forensic evidence, not proof of authenticity.
- EXIF presence does not prove an image is original.
- EXIF absence does not prove an image is edited.
- "Adobe Photoshop" in software field is evidence, not a manipulation verdict.
- Timestamps in EXIF can be set to any value.

## Registration and Crop (Phases 4–5)

- Platform simulation profiles (WhatsApp-like, Instagram-like) are approximations, not exact reproductions of proprietary pipelines.
- Heavy crops (>80%) may produce INCONCLUSIVE due to limited feature overlap.
- Very small crops (<2%) may be indistinguishable from registration error.
- Crop percentage is an estimate — error increases with registration uncertainty.

## Evidence Fusion (Phase 8)

- Fusion weights are heuristic and UNCALIBRATED.
- No calibrated probability is produced until a validated calibration dataset exists.
- Evidence groups reduce double-counting but cannot eliminate correlated signals entirely.
- The fusion model (fusion_logistic_v1) has not been independently validated.

## Tamper-Evidence

- The sealed record uses SHA-256 hashing — it is TAMPER_EVIDENT, not TAMPER_PROOF.
- Hash chaining provides sequential integrity but not blockchain-level immutability.
- There is no timestamping authority or PKI integration in this version.

## Platform & Environment

- The Python forensic service must be running and reachable for full analysis.
- Without a PostgreSQL database, results are not persisted across sessions.
- Storage falls back to local filesystem when Supabase is not configured.
- GPU training is supported but not tested on the development machine (CPU-only install).

## What This System Does NOT Provide

- Legal proof of authenticity or manipulation
- Guaranteed detection of all AI-generated content
- Identification of specific editing tools or actors
- Real-time analysis (processing takes seconds to minutes)
- Support for all image formats (JPEG, PNG, WebP only currently)
- Production-grade availability guarantees
