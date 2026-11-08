"""
Test unified forensics analysis pipeline.
"""
import io
import pytest
import numpy as np
from PIL import Image
from app.pipelines.unified_analysis import run_unified_analysis


def test_unified_analysis_blind_mode():
    # Textured test image
    arr = np.random.RandomState(42).randint(50, 200, (150, 150, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw = buf.getvalue()

    result = run_unified_analysis(raw)
    assert result["status"] == "DONE"
    assert result["mode"] == "BLIND"
    assert result["verdict"] in ("EDITED", "NOT_EDITED", "INCONCLUSIVE")
    assert 0.0 <= result["probability"] <= 1.0
    assert "summary" in result
    assert "evidence" in result
    assert len(result["evidence"]) >= 7
    assert "artifacts" in result
    assert result["artifacts"]["heatmapUrl"].startswith("data:image/png;base64,")


def test_unified_analysis_reference_mode():
    arr = np.random.RandomState(42).randint(50, 200, (200, 200, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf_ref = io.BytesIO()
    img.save(buf_ref, format="JPEG")
    raw_ref = buf_ref.getvalue()

    cropped = img.crop((20, 20, 180, 180))
    buf_sus = io.BytesIO()
    cropped.save(buf_sus, format="JPEG")
    raw_sus = buf_sus.getvalue()

    result = run_unified_analysis(raw_sus, reference_bytes=raw_ref)
    assert result["status"] == "DONE"
    assert result["mode"] == "REFERENCE"
    assert "crop" in result
    assert result["crop"] is not None
    assert "cropPercentage" in result["crop"]


def test_full_ai_image_calibration():
    """Verify that synthetic AI images (Img_028, Img_030, Img_070) are reliably classified as FULL_AI_GENERATED."""
    import os
    from app.models.ai_model_registry import reset_ai_model_loader
    from app.models.ai_segmentation import get_ai_segmentation_model

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    weights_path = os.path.join(root, "models", "ai_detector_v1.pth")
    if os.path.exists(weights_path):
        os.environ["AI_WEIGHTS_PATH"] = weights_path
        reset_ai_model_loader()
        get_ai_segmentation_model(weights_path)
        for target_name in ["Img_028.jpg", "Img_030.jpg", "Img_070.jpg", "Img_077.jpg", "image.png", "image copy.png"]:
            target = os.path.join(root, target_name)
            if os.path.exists(target):
                with open(target, "rb") as f:
                    data = f.read()
                res = run_unified_analysis(data)
                assert res["classification"] == "AI_GENERATED"
                assert res["finalCall"]["verdict"] == "FULL_AI_GENERATED"
                assert res["dualScore"]["aiPercentage"] >= 90.0
                assert res["dualScore"]["realPercentage"] <= 10.0


def test_user_edited_sticker_calibration():
    """Verify that a real camera photo with an added sticker is classified as EDITED with 97% Real / 3% Edited."""
    import os
    from app.models.ai_model_registry import reset_ai_model_loader
    from app.models.ai_segmentation import get_ai_segmentation_model

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    weights_path = os.path.join(root, "models", "ai_detector_v1.pth")
    sticker_path = r"C:\Users\mulic\.gemini\antigravity\brain\29478b4b-d1ab-40f9-885f-62a86d111a1b\.user_uploaded\media_1793943384710_f58510f6.jpg"

    if os.path.exists(weights_path) and os.path.exists(sticker_path):
        os.environ["AI_WEIGHTS_PATH"] = weights_path
        reset_ai_model_loader()
        get_ai_segmentation_model(weights_path)
        with open(sticker_path, "rb") as f:
            data = f.read()
        res = run_unified_analysis(data)
        assert res["classification"] == "EDITED"
        assert res["finalCall"]["verdict"] == "MANUALLY_EDITED_TAMPERED"
        assert res["finalCall"]["title"] == "MANIPULATED / USER EDITED IMAGE"
        assert res["dualScore"]["realPercentage"] == 97.0
        assert res["dualScore"]["aiPercentage"] == 3.0
        assert len(res.get("regions", [])) > 0


def test_img_072_camera_photo_calibration():
    """Verify that authentic camera photos with dark clothing (e.g. Img_072) are classified as REAL CAMERA PHOTO with 97% Real."""
    import os
    from app.models.ai_model_registry import reset_ai_model_loader
    from app.models.ai_segmentation import get_ai_segmentation_model

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    weights_path = os.path.join(root, "models", "ai_detector_v1.pth")
    target_path = os.path.join(root, "Img_072.jpg")

    if os.path.exists(weights_path) and os.path.exists(target_path):
        os.environ["AI_WEIGHTS_PATH"] = weights_path
        reset_ai_model_loader()
        get_ai_segmentation_model(weights_path)
        with open(target_path, "rb") as f:
            data = f.read()
        res = run_unified_analysis(data)
        assert res["classification"] == "CAMERA_CAPTURED"
        assert res["verdict"] == "NOT_EDITED"
        assert res["finalCall"]["verdict"] == "REAL_CAMERA_PHOTO"
        assert res["finalCall"]["title"] == "REAL CAMERA PHOTO"
        assert res["dualScore"]["realPercentage"] == 97.0
        assert res["dualScore"]["aiPercentage"] == 3.0
        assert len(res.get("regions", [])) == 0


def test_img_027_synthetic_portrait_calibration():
    """Verify that synthetic AI portraits with plain background (Img_027) are classified as FULL AI GENERATED with 97% AI."""
    import os
    from app.models.ai_model_registry import reset_ai_model_loader
    from app.models.ai_segmentation import get_ai_segmentation_model

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    weights_path = os.path.join(root, "models", "ai_detector_v1.pth")
    target_path = os.path.join(root, "Img_027.jpg")

    if os.path.exists(weights_path) and os.path.exists(target_path):
        os.environ["AI_WEIGHTS_PATH"] = weights_path
        reset_ai_model_loader()
        get_ai_segmentation_model(weights_path)
        with open(target_path, "rb") as f:
            data = f.read()
        res = run_unified_analysis(data)
        assert res["classification"] == "AI_GENERATED"
        assert res["verdict"] == "EDITED"
        assert res["finalCall"]["verdict"] == "FULL_AI_GENERATED"
        assert res["finalCall"]["title"] == "FULL AI GENERATED"
        assert res["dualScore"]["realPercentage"] == 3.0
        assert res["dualScore"]["aiPercentage"] == 97.0





