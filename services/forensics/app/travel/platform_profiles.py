"""
Platform-Like Transformation Profiles — Phase 7.

DISCLAIMER: These profiles SIMULATE common transformations and are NOT
guaranteed replicas of proprietary production pipelines. They model
typical behaviors documented in public research and testing.

Profile names use suffixes like "_LIKE" to clarify they are approximations.
"""
from __future__ import annotations

from app.travel.generator import TransformStep


def _profile(name: str, steps: list[TransformStep], description: str) -> dict:
    return {"name": name, "steps": steps, "description": description,
            "disclaimer": "Simulation only. Not an exact replica of any proprietary pipeline."}


PLATFORM_PROFILES = {

    "WHATSAPP_LIKE": _profile(
        name="WHATSAPP_LIKE",
        steps=[
            TransformStep("RESIZE", {"scale": 0.75}, "Resize to approx 75%"),
            TransformStep("JPEG_RECOMPRESSION", {"quality": 75}, "JPEG re-encode at q=75"),
            TransformStep("METADATA_CHANGE", {"action": "STRIP"}, "Strip EXIF metadata"),
        ],
        description="Simulates typical WhatsApp-like image sending (resize + JPEG compression + metadata strip).",
    ),

    "INSTAGRAM_LIKE": _profile(
        name="INSTAGRAM_LIKE",
        steps=[
            TransformStep("RESIZE", {"scale": 0.80}, "Resize to approx 80%"),
            TransformStep("JPEG_RECOMPRESSION", {"quality": 80}, "JPEG re-encode at q=80"),
            TransformStep("COLOR_CHANGE", {"saturation": 1.15, "temperature_shift": 5},
                          "Mild color enhancement"),
            TransformStep("METADATA_CHANGE", {"action": "STRIP"}, "Strip EXIF metadata"),
        ],
        description="Simulates Instagram-like image sharing (resize + JPEG + color enhancement + metadata strip).",
    ),

    "GENERIC_SOCIAL_MEDIA": _profile(
        name="GENERIC_SOCIAL_MEDIA",
        steps=[
            TransformStep("RESIZE", {"scale": 0.70}, "Resize to 70%"),
            TransformStep("JPEG_RECOMPRESSION", {"quality": 70}, "JPEG re-encode at q=70"),
            TransformStep("METADATA_CHANGE", {"action": "STRIP"}, "Strip EXIF"),
        ],
        description="Generic social media sharing simulation.",
    ),

    "GENERIC_MESSAGING": _profile(
        name="GENERIC_MESSAGING",
        steps=[
            TransformStep("JPEG_RECOMPRESSION", {"quality": 80}, "JPEG re-encode"),
            TransformStep("METADATA_CHANGE", {"action": "STRIP"}, "Strip EXIF"),
        ],
        description="Generic messaging app simulation (no resize, moderate compression).",
    ),

    "SCREENSHOT_LIKE": _profile(
        name="SCREENSHOT_LIKE",
        steps=[
            TransformStep("SCREENSHOT", {"padding": 30, "quality": 85, "format": "JPEG"},
                          "Screenshot simulation with padding"),
            TransformStep("JPEG_RECOMPRESSION", {"quality": 80}, "JPEG re-encode"),
        ],
        description="Screenshot-like transformation with padding and re-encoding.",
    ),

    "IDENTITY": _profile(
        name="IDENTITY",
        steps=[TransformStep("NONE", {}, "No transformation applied")],
        description="Identity transform (negative control — no changes).",
    ),

    "JPEG_ONLY_Q85": _profile(
        name="JPEG_ONLY_Q85",
        steps=[TransformStep("JPEG_RECOMPRESSION", {"quality": 85}, "JPEG recompress q=85")],
        description="Negative control — JPEG recompression only.",
    ),

    "JPEG_ONLY_Q75": _profile(
        name="JPEG_ONLY_Q75",
        steps=[TransformStep("JPEG_RECOMPRESSION", {"quality": 75}, "JPEG recompress q=75")],
        description="Negative control — JPEG recompression only.",
    ),

    "JPEG_ONLY_Q60": _profile(
        name="JPEG_ONLY_Q60",
        steps=[TransformStep("JPEG_RECOMPRESSION", {"quality": 60}, "JPEG recompress q=60")],
        description="Negative control — aggressive JPEG recompression.",
    ),

    "RESIZE_ONLY_75": _profile(
        name="RESIZE_ONLY_75",
        steps=[TransformStep("RESIZE", {"scale": 0.75}, "Resize to 75%")],
        description="Negative control — resize only.",
    ),

    "RESIZE_ONLY_50": _profile(
        name="RESIZE_ONLY_50",
        steps=[TransformStep("RESIZE", {"scale": 0.50}, "Resize to 50%")],
        description="Negative control — resize to 50%.",
    ),

    "METADATA_STRIP_ONLY": _profile(
        name="METADATA_STRIP_ONLY",
        steps=[TransformStep("METADATA_CHANGE", {"action": "STRIP"}, "Strip EXIF only")],
        description="Negative control — metadata removal only.",
    ),
}


def get_profile(name: str) -> dict:
    """Get a platform profile by name."""
    if name not in PLATFORM_PROFILES:
        raise ValueError(f"Unknown profile: {name}. Available: {list(PLATFORM_PROFILES.keys())}")
    return PLATFORM_PROFILES[name]


def list_profiles() -> list[str]:
    return list(PLATFORM_PROFILES.keys())
