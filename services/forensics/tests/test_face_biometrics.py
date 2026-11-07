import os
import cv2
import numpy as np
import pytest

from app.detectors.face_biometrics import (
    FaceBiometricsDetector,
    get_face_biometrics_detector,
    DETECTOR_NAME,
    DETECTOR_VERSION,
)


def test_face_biometrics_contract():
    detector = get_face_biometrics_detector()
    assert detector.name == DETECTOR_NAME
    assert detector.version == DETECTOR_VERSION
    assert detector.category.value == "AI_GENERATED"


def test_face_biometrics_no_face():
    detector = get_face_biometrics_detector()
    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", blank)
    res = detector.run("", image_bytes=buf.tobytes())
    assert res.details["status"] == "NO_FACES_DETECTED"
    assert res.details["face_count"] == 0
    assert res.confidence == 0.0


def test_face_biometrics_on_synthetic_face_if_present():
    detector = get_face_biometrics_detector()
    target = "Img_030.jpg"
    if os.path.exists(target):
        with open(target, "rb") as f:
            b = f.read()
        res = detector.run("", image_bytes=b)
        if res.details["face_count"] > 0:
            assert res.details["status"] == "SYNTHETIC_FACIAL_ARTIFACTS"
            assert res.score >= 0.80


def test_face_biometrics_on_real_portrait_if_present():
    detector = get_face_biometrics_detector()
    target = r"C:\Users\mulic\.gemini\antigravity\brain\29478b4b-d1ab-40f9-885f-62a86d111a1b\my_pic01.jpg"
    if os.path.exists(target):
        with open(target, "rb") as f:
            b = f.read()
        res = detector.run("", image_bytes=b)
        if res.details["face_count"] > 0:
            assert res.details["status"] == "NATURAL_BIOMETRIC_VERIFIED"
            assert res.score <= 0.15

