import sys
import os
from pathlib import Path

# Add services/forensics directory so that 'app.main' and its submodules resolve cleanly
ROOT_DIR = Path(__file__).resolve().parent
FORENSICS_DIR = ROOT_DIR / "services" / "forensics"
if str(FORENSICS_DIR) not in sys.path:
    sys.path.insert(0, str(FORENSICS_DIR))

# Ensure AI_WEIGHTS_PATH is set if not already present
if not os.environ.get("AI_WEIGHTS_PATH"):
    default_model = ROOT_DIR / "models" / "ai_detector_v1.pth"
    if default_model.is_file():
        os.environ["AI_WEIGHTS_PATH"] = str(default_model)

from app.main import app

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
