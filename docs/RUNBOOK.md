# PINITHUB FORENSICS — Operational Runbook

This runbook guides engineers on starting, developing, testing, inspecting jobs, and operating the system, conforming to Section 9 and Section 16 of `PinITHUB_Plan.pdf`.

---

## 1. Quick Start (< 5 Minutes)

### Prerequisites
- Node.js 20 LTS
- Python 3.11 with a virtual environment

### Step 1: Install Dependencies
```bash
# Install Node dependencies
npm install

# Setup Python forensics environment
cd services/forensics
.venv\Scripts\activate   # Windows (.venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
cd ../..
```

### Step 2: Start Services
You can run each service independently or in parallel terminals:

**Terminal 1 — Python Forensics Service:**
```bash
cd services/forensics
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8001
# → Running at http://localhost:8001
```

**Terminal 2 — Node.js API:**
```bash
npm run dev:api
# → Running at http://localhost:4000
```

**Terminal 3 — React Frontend:**
```bash
npm run dev:web
# → Running at http://localhost:5173
```

**Terminal 4 (Optional) — Forensics Background Worker Daemon:**
```bash
cd services/forensics
.venv\Scripts\activate
python -m app.worker
```

---

## 2. Running Tests & Verifications

```bash
# 1. Run all Python Forensics tests (270+ tests covering all detectors & pipelines)
services\forensics\.venv\Scripts\pytest services\forensics\tests

# 2. Run Web Frontend tests (Vitest)
npm run test:web

# 3. Check TypeScript contracts across workspaces
npm run test:shared
npm --workspace @pinithub/web run build
npm --workspace @pinithub/api run build

# 4. Run the Crop Evaluation Benchmark (Crop_plan.pdf validation)
cd services/forensics
.venv\Scripts\python -m app.utils.crop_evaluation
```

---

## 3. How to Inspect Jobs & Forensics Flow

### Single Image Blind Analysis:
1. Open `http://localhost:5173`.
2. Drag and drop any test image into **1. Suspect Image**.
3. Click **"Run Forensic Analysis"**.
4. View the real-time verdict, calibrated probability, interactive tampering heatmap with opacity slider, candidate regions table, and evidence breakdown.

### Reference & Crop Analysis:
1. Check the box **"Reference & Crop Mode"**.
2. Select or upload the **Original Image**.
3. Select or upload the **Cropped / Suspect Copy**.
4. Click **"Run Forensic Analysis"**.
5. The system computes homography, inverse corner projection, and displays:
   - Exact crop percentage cut away (e.g. 45.2% removed).
   - Kept area percentage.
   - Bounding box coordinates on the original image.

