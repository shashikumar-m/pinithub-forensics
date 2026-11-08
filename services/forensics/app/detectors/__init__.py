"""
Detectors package — forensic detector interfaces and implementations.

Phase 3: All 7 classical detectors implemented.
"""
from app.detectors.base import BaseDetector, DetectorResult, DetectorCategory
from app.detectors.metadata_inspector import MetadataInspector, get_metadata_inspector
from app.detectors.ela import ELADetector, get_ela_detector
from app.detectors.noise_residual import NoiseResidualDetector, get_noise_residual_detector
from app.detectors.dct_analysis import DCTAnalysisDetector, get_dct_analysis_detector
from app.detectors.jpeg_double_compression import JPEGDoubleCompressionDetector, get_jpeg_double_compression_detector
from app.detectors.resampling import ResamplingDetector, get_resampling_detector
from app.detectors.jpeg_grid import JPEGGridDetector, get_jpeg_grid_detector
from app.detectors.copy_move import CopyMoveDetector, get_copy_move_detector
from app.detectors.univfd import UnivFDDetector, get_univfd_detector
from app.detectors.drct import DRCTDetector, get_drct_detector

__all__ = [
    "BaseDetector", "DetectorResult", "DetectorCategory",
    "MetadataInspector", "get_metadata_inspector",
    "ELADetector", "get_ela_detector",
    "NoiseResidualDetector", "get_noise_residual_detector",
    "DCTAnalysisDetector", "get_dct_analysis_detector",
    "JPEGDoubleCompressionDetector", "get_jpeg_double_compression_detector",
    "ResamplingDetector", "get_resampling_detector",
    "JPEGGridDetector", "get_jpeg_grid_detector",
    "CopyMoveDetector", "get_copy_move_detector",
    "UnivFDDetector", "get_univfd_detector",
    "DRCTDetector", "get_drct_detector",
]
