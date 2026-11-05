"""
Detector interface contract for the PINITHUB forensic service.

This module defines the abstract base class that all forensic detectors
must implement. It establishes the contract for detector results so
that the pipeline can process outputs uniformly.

Phase 0: Only the interface is defined. No actual detectors are implemented.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time


class DetectorCategory(str, Enum):
    """Forensic detector categories."""
    AI_GENERATED = "AI_GENERATED"
    AI_EDITED = "AI_EDITED"
    ELA = "ELA"
    NOISE_RESIDUAL = "NOISE_RESIDUAL"
    DCT = "DCT"
    JPEG_DOUBLE_COMPRESSION = "JPEG_DOUBLE_COMPRESSION"
    COPY_MOVE = "COPY_MOVE"
    KEYPOINT_MATCH = "KEYPOINT_MATCH"
    CROP_PERCENTAGE = "CROP_PERCENTAGE"
    TRAVELLED_COPY = "TRAVELLED_COPY"
    METADATA = "METADATA"


@dataclass
class DetectorResult:
    """
    The output of running a single forensic detector.

    This structure mirrors the DetectorOutput record in the database
    and the TypeScript type in @pinithub/shared.
    """
    detector: str
    version: str
    category: DetectorCategory
    score: Optional[float] = None
    confidence: Optional[float] = None
    # Path to a heatmap or mask artifact (object storage path), when available
    map_path: Optional[str] = None
    # Binary mask as a numpy array, when produced in-memory (not persisted yet)
    mask: Optional[Any] = None
    # Detector-specific structured evidence
    details: dict[str, Any] = field(default_factory=dict)
    # Execution time in milliseconds
    execution_time_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary suitable for JSON responses."""
        return {
            "detector": self.detector,
            "version": self.version,
            "category": self.category.value,
            "score": self.score,
            "confidence": self.confidence,
            "map_path": self.map_path,
            "details": self.details,
            "execution_time_ms": self.execution_time_ms,
        }


class BaseDetector(ABC):
    """
    Abstract base class for all forensic detectors.

    Subclasses must implement:
      - name: detector identifier (e.g. "ela")
      - version: detector version string (e.g. "1.0.0")
      - category: DetectorCategory
      - run(image_path) -> DetectorResult

    The detector must NOT store or log sensitive image contents.
    The detector must report honest results — no fabricated scores.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Detector identifier, e.g. 'ela'."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Detector version, e.g. '1.0.0'."""
        ...

    @property
    @abstractmethod
    def category(self) -> DetectorCategory:
        """Forensic category this detector belongs to."""
        ...

    @abstractmethod
    def run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        """
        Run the detector on an image.

        Args:
            image_path: Path to the image file (or object-storage key).
            **kwargs: Additional detector-specific parameters.

        Returns:
            DetectorResult with honest scores and evidence.
        """
        ...

    def timed_run(self, image_path: str, **kwargs: Any) -> DetectorResult:
        """Run the detector and record execution time."""
        start = time.perf_counter()
        result = self.run(image_path, **kwargs)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        result.execution_time_ms = elapsed_ms
        return result
