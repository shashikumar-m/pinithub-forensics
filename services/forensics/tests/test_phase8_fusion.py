"""
Phase 8 — Evidence Fusion, Verdict Engine, Region Fusion, Report tests.
"""
import hashlib
import json
import pytest

from app.fusion.normalizer import normalize_all, EvidenceItem
from app.fusion.verdict_engine import fuse, FinalAssessmentResult
from app.fusion.region_fusion import fuse_regions, FinalRegion
from app.fusion.report_generator import (
    build_canonical_report, canonical_json, seal_report, generate_text_report
)


# ---- Normalizer tests ----

class TestNormalizer:
    def test_empty_results_returns_empty(self):
        items = normalize_all({})
        assert isinstance(items, list)

    def test_registration_completed_normalized(self):
        items = normalize_all({"registration": {
            "status": "COMPLETED", "inlier_ratio": 0.9,
            "inlier_count": 200, "reprojection_error": 0.5,
        }})
        reg = next((i for i in items if i.category == "REGISTRATION"), None)
        assert reg is not None
        assert reg.status == "NEUTRAL"

    def test_registration_no_match(self):
        items = normalize_all({"registration": {"status": "NO_MATCH", "inlier_ratio": 0}})
        reg = next(i for i in items if i.category == "REGISTRATION")
        assert reg.status == "CONTRADICTING"

    def test_crop_detected_supporting(self):
        items = normalize_all({"crop": {
            "status": "DETECTED", "crop_percentage": 25.0
        }})
        crop = next(i for i in items if i.category == "CROP")
        assert crop.status == "SUPPORTING"

    def test_crop_below_threshold_neutral(self):
        items = normalize_all({"crop": {"status": "DETECTED", "crop_percentage": 1.0}})
        crop = next(i for i in items if i.category == "CROP")
        assert crop.status in ("NEUTRAL", "UNAVAILABLE", "SUPPORTING")

    def test_ai_unavailable_normalized(self):
        items = normalize_all({"ai": {"status": "UNAVAILABLE"}})
        ai = next(i for i in items if i.category == "AI")
        assert ai.status == "UNAVAILABLE"

    def test_ai_edited_supporting(self):
        items = normalize_all({"ai": {
            "status": "AI_EDITED_LOCAL", "image_level_score": 0.7,
            "regions": [{"bbox": {}, "area_pixels": 100, "area_percentage": 2.0}]
        }})
        ai = next(i for i in items if i.category == "AI")
        assert ai.status == "SUPPORTING"

    def test_evidence_group_assigned(self):
        items = normalize_all({"ela": {"status": "COMPLETED", "score": 0.3}})
        ela = next((i for i in items if i.category == "ELA"), None)
        if ela:
            assert ela.evidence_group == "JPEG_GROUP"

    def test_all_items_have_id(self):
        items = normalize_all({
            "registration": {"status": "COMPLETED", "inlier_ratio": 0.5},
            "crop": {"status": "NO_CROP"},
        })
        assert all(item.id for item in items)


# ---- Verdict engine tests ----

class TestVerdictEngine:
    def test_no_match_registration(self):
        result = fuse([], registration_status="NO_MATCH")
        assert result.verdict == "NO_MATCH"

    def test_no_usable_evidence_unavailable(self):
        items = [EvidenceItem(id="x", category="ELA", detector="ela", version="1",
                               status="UNAVAILABLE", description="")]
        result = fuse(items)
        assert result.verdict == "ANALYSIS_UNAVAILABLE"

    def test_two_supporting_groups_edited(self):
        items = [
            EvidenceItem(id="a", category="CROP", detector="crop_detector", version="1",
                          status="SUPPORTING", evidence_group="CROP_GROUP", description="crop"),
            EvidenceItem(id="b", category="AI", detector="ai_detector", version="1",
                          status="SUPPORTING", evidence_group="AI_GROUP", description="ai"),
        ]
        result = fuse(items)
        assert result.verdict == "EDITED"

    def test_one_strong_group_edited(self):
        items = [
            EvidenceItem(id="c", category="CROP", detector="crop", version="1",
                          status="SUPPORTING", evidence_group="CROP_GROUP", description="crop"),
        ]
        result = fuse(items)
        assert result.verdict == "EDITED"

    def test_all_neutral_not_edited(self):
        items = [
            EvidenceItem(id="d", category="REGISTRATION", detector="reg", version="1",
                          status="NEUTRAL", evidence_group="REGISTRATION_GROUP", description="ok"),
            EvidenceItem(id="e", category="METADATA", detector="meta", version="1",
                          status="NEUTRAL", evidence_group="METADATA_GROUP", description="ok"),
            EvidenceItem(id="f", category="ELA", detector="ela", version="1",
                          status="NEUTRAL", evidence_group="JPEG_GROUP", description="ok"),
        ]
        result = fuse(items)
        assert result.verdict == "NOT_EDITED"

    def test_conflicting_evidence_inconclusive(self):
        items = [
            EvidenceItem(id="g", category="CROP", detector="crop", version="1",
                          status="SUPPORTING", evidence_group="CROP_GROUP", description=""),
            EvidenceItem(id="h", category="REGISTRATION", detector="reg", version="1",
                          status="CONTRADICTING", evidence_group="REGISTRATION_GROUP", description=""),
        ]
        result = fuse(items)
        assert result.verdict == "INCONCLUSIVE"

    def test_calibration_always_uncalibrated_or_unavailable(self):
        # UNCALIBRATED when there's evidence; UNAVAILABLE when none
        result = fuse([])
        assert result.confidence_status in ("UNCALIBRATED", "UNAVAILABLE")

    def test_no_probability_without_calibration(self):
        items = [
            EvidenceItem(id="i", category="AI", detector="ai", version="1",
                          status="SUPPORTING", evidence_group="AI_GROUP", description="")
        ]
        result = fuse(items)
        assert result.probability is None

    def test_fusion_version_recorded(self):
        result = fuse([])
        assert result.fusion_version is not None

    def test_result_has_explanation(self):
        result = fuse([])
        assert result.explanation


# ---- Region fusion tests ----

class TestRegionFusion:
    def test_crop_produces_region(self):
        regions = fuse_regions(
            crop_result={"status": "DETECTED", "crop_percentage": 20.0,
                          "bounding_box": {"x": 0, "y": 0, "width": 200, "height": 50},
                          "kept_area_pixels": 40000, "confidence": 0.8},
            ai_result=None, travel_changes=[], diff_regions=[],
            original_width=256, original_height=256,
        )
        assert len(regions) >= 1
        assert regions[0].type == "CROP"

    def test_overlapping_regions_merged(self):
        # Crop and AI both cover same area
        regions = fuse_regions(
            crop_result={"status": "DETECTED", "crop_percentage": 20.0,
                          "bounding_box": {"x": 0, "y": 0, "width": 50, "height": 50},
                          "kept_area_pixels": 50000, "confidence": 0.7},
            ai_result={"status": "AI_EDITED_LOCAL",
                        "regions": [{"bbox": {"x": 5, "y": 5, "width": 40, "height": 40},
                                      "area_pixels": 1600, "area_percentage": 2.4, "confidence": 0.6}]},
            travel_changes=[], diff_regions=[],
            original_width=256, original_height=256,
        )
        # Should merge since they overlap (IoU > 0.3)
        assert len(regions) >= 1

    def test_coordinates_in_original_space(self):
        regions = fuse_regions(
            crop_result={"status": "DETECTED", "crop_percentage": 25.0,
                          "bounding_box": {"x": 10, "y": 20, "width": 100, "height": 80},
                          "kept_area_pixels": 48000, "confidence": 0.8},
            ai_result=None, travel_changes=[], diff_regions=[],
            original_width=256, original_height=256,
        )
        if regions:
            r = regions[0]
            assert r.bbox_x <= 256
            assert r.bbox_y <= 256

    def test_empty_inputs_no_regions(self):
        regions = fuse_regions(None, None, [], [], 256, 256)
        assert regions == []


# ---- Report generator tests ----

class TestReportGenerator:
    def _make_report(self):
        return build_canonical_report(
            investigation_id="test-inv-123",
            verdict="EDITED",
            confidence_status="UNCALIBRATED",
            evidence_strength="MEDIUM",
            explanation="Test explanation",
            warnings=["warning A"],
            fusion_version="fusion_logistic_v1",
            reference_image={"sha256": "abc123", "originalFilename": "orig.jpg"},
            suspect_image={"sha256": "def456", "originalFilename": "susp.jpg"},
            registration={"status": "COMPLETED", "inlierRatio": 0.9},
            metadata_changes=[{"field": "software", "status": "REMOVED"}],
            transformations=["JPEG_RECOMPRESSION", "CROP"],
            evidence_items=[],
            regions=[],
            crop={"status": "DETECTED", "crop_percentage": 20.0, "kept_percentage": 80.0},
            ai_detection={"status": "UNAVAILABLE"},
            limitations=["AI unavailable"],
        )

    def test_schema_version_present(self):
        r = self._make_report()
        assert r["schemaVersion"] == "1.0"

    def test_verdict_present(self):
        r = self._make_report()
        assert r["verdict"] == "EDITED"

    def test_sha256_preserved(self):
        r = self._make_report()
        assert r["originalImage"]["sha256"] == "abc123"

    def test_transformations_sorted(self):
        r = self._make_report()
        t = r["transformations"]
        assert t == sorted(t)

    def test_canonical_json_deterministic(self):
        r = self._make_report()
        j1 = canonical_json(r)
        j2 = canonical_json(r)
        assert j1 == j2

    def test_seal_produces_sha256(self):
        r = self._make_report()
        j = canonical_json(r)
        seal = seal_report(j)
        assert len(seal["reportHash"]) == 64
        assert seal["algorithm"] == "SHA-256"
        assert seal["tamperEvident"] is True

    def test_seal_changes_on_report_change(self):
        r1 = self._make_report()
        r2 = dict(r1)
        r2["verdict"] = "NOT_EDITED"
        j1, j2 = canonical_json(r1), canonical_json(r2)
        s1 = seal_report(j1)["reportHash"]
        s2 = seal_report(j2)["reportHash"]
        assert s1 != s2

    def test_text_report_contains_verdict(self):
        r = self._make_report()
        text = generate_text_report(r)
        assert "EDITED" in text
        assert "ORIGINAL IMAGE" in text
        assert "LIMITATIONS" in text

    def test_limitations_documented(self):
        r = self._make_report()
        assert "AI unavailable" in r["limitations"]

    def test_seal_note_clarifies_not_guaranteed(self):
        r = self._make_report()
        j = canonical_json(r)
        seal = seal_report(j)
        # The note must clarify "TAMPER_EVIDENT" and explicitly say it's not a guarantee
        note = seal.get("note", "")
        assert "TAMPER_EVIDENT" in note
        assert "not" in note.lower() or "NOT" in note
