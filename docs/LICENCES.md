# License Register

This document tracks all external algorithms, deep learning models, software libraries, and public datasets used in the **PINITHUB FORENSICS** platform, strictly fulfilling Section 1.1 and Section 16 (Checklist Item 8) of `PinITHUB_Plan.pdf`.

---

## 1. Forensic Models & Algorithms

| Model / Algorithm | Paper / Origin | License | Commercial Use Allowed? | Production Status | Notes |
|---|---|---|---|---|---|
| **Error Level Analysis (ELA)** | Krawetz (2007) | Open Implementation | Yes | [PROVEN, LIMITED] | Recompression error metric |
| **Noise Residual Analysis** | Cozzolino et al. (2015) | Open Implementation | Yes | [PROVEN] | Median filter residual variance |
| **DCT Coefficient Analysis** | Bianchi & Piva (2012) | Open Implementation | Yes | [PROVEN] | JPEG coefficient histogram analysis |
| **Double JPEG Compression** | Popescu & Farid (2005) | Open Implementation | Yes | [PROVEN] | Frequency domain grid checking |
| **Resampling Detection** | Kirchner (2008) | Open Implementation | Yes | [PROVEN] | Periodic interpolation correlations |
| **Copy-Move (SIFT/ORB + RANSAC)** | Amerini et al. (2011) | BSD-3-Clause / Apache 2.0 (OpenCV) | Yes | [PROVEN] | Keypoint matching with homography |
| **Crop Percentage Detector** | PinIt Technical Brief | Internal / Apache 2.0 | Yes | [PROVEN] | Homography inverse corner projection |
| **UNet + EfficientNet-B3 Segmentation** | segmentation-models-pytorch | MIT License | Yes | [EXPERIMENTAL] | Own trained weights; owned by PinIt |
| **TruFor** | Guillaro et al. (CVPR 2023) | Creative Commons Non-Commercial (CC BY-NC 4.0) | **NO** (Research Only) | Benchmark Only | Used strictly for offline validation |
| **CAT-Net** | Kwon et al. (IJCV 2022) | Academic Research License | **NO** (Research Only) | Benchmark Only | DCT stream analysis baseline |
| **Noiseprint** | Cozzolino & Verdoliva (2020) | Research License | **NO** | Benchmark Only | Learned camera model noise pattern |

---

## 2. Public Datasets

| Dataset | Creators | License | Purpose in Project |
|---|---|---|---|
| **CASIA v2** | Dong et al. (2013) | Academic Research Use Only | Splicing & copy-move baseline evaluation |
| **Columbia Uncompressed** | Hsu & Chang (2006) | Research License | Testing noise-based detectors on raw splices |
| **COVERAGE** | Wen et al. (2016) | Research License | Copy-move evaluation with genuine similar objects |
| **IMD2020** | Novozamsky et al. (2020) | CC BY-NC 4.0 | Realistic real-world manipulation testing |
| **DEFACTO** | Mahfoudi et al. (2019) | Academic / Research | Synthetic copy-move, splicing, and inpainting on COCO |
| **TGIF** | Mareen et al. (2024) | Research License | Text-guided inpainting with multiple diffusion backbones |
| **GenImage** | Zhu et al. (2023) | Research License | Fully AI-generated image classification benchmarks |
| **RAISE** | Dang-Nguyen et al. (2015) | Academic License | 8,000 unedited camera originals for false-positive rate (FPR) testing |

---

## 3. Core Software Libraries & Frameworks

| Package | Ecosystem | License | Approved |
|---|---|---|---|
| **React 18** | Frontend | MIT | Yes |
| **Vite 5** | Frontend | MIT | Yes |
| **Tailwind CSS 3** | Frontend | MIT | Yes |
| **Node.js 20** | API Server | MIT | Yes |
| **Express 4** | API Server | MIT | Yes |
| **Prisma 5** | ORM | Apache 2.0 | Yes |
| **FastAPI** | Forensics Service | MIT | Yes |
| **PyTorch 2** | Machine Learning | Modified BSD | Yes |
| **OpenCV 4 (headless)** | Computer Vision | Apache 2.0 | Yes |
| **NumPy & SciPy** | Numerics | BSD-3-Clause | Yes |
| **Pillow (PIL)** | Image I/O | HPND (Historical Permission) | Yes |
| **Zod** | Validation | MIT | Yes |

