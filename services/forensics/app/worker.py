"""
Forensics Background Worker Daemon — Phase 2.

Follows PinITHUB_Plan.pdf (Section 3.1, 3.2, 7.3, 11):
- Continuously polls for queued analysis jobs using SKIP LOCKED semantics.
- Claims jobs safely with crash recovery (reclaiming stale locks >15 min).
- Executes the unified forensic pipeline (classical + AI + reference comparison + crop).
- Writes results, evidence, regions, and artifacts back.
- Graceful shutdown on SIGINT/SIGTERM.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from typing import Optional
import urllib.request
import json

from app.config import get_settings
from app.pipelines.unified_analysis import run_unified_analysis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [worker] %(message)s",
)
logger = logging.getLogger("pinithub-worker")


class ForensicsWorker:
    """Worker daemon that claims and executes image forensic analysis jobs."""

    def __init__(self, worker_id: Optional[str] = None):
        self.settings = get_settings()
        self.worker_id = worker_id or os.environ.get("WORKER_ID", f"worker-{os.getpid()}")
        self.api_url = os.environ.get("API_URL", self.settings.api_url).rstrip("/")
        self.poll_interval = int(os.environ.get("WORKER_POLL_INTERVAL", "3"))
        self.running = True

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    def claim_job_from_api(self) -> Optional[dict]:
        """Claim the next queued job from the API."""
        url = f"{self.api_url}/v1/jobs/claim"
        req = urllib.request.Request(
            url,
            data=json.dumps({"workerId": self.worker_id}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("job")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                logger.warning(f"Error checking for jobs from API: {e.code}")
        except Exception:
            # API might not be running or no jobs queued
            pass
        return None

    def complete_job_to_api(self, job_id: str, analysis_id: str, result: dict) -> bool:
        """Report completed analysis result back to API."""
        url = f"{self.api_url}/v1/jobs/{job_id}/complete"
        payload = {
            "workerId": self.worker_id,
            "analysisId": analysis_id,
            "result": result,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to submit completed job {job_id} to API: {e}")
            return False

    def process_job(self, job: dict):
        """Process a claimed job."""
        job_id = job["id"]
        analysis_id = job["analysisId"]
        suspect_hex = job.get("imageHex")
        reference_hex = job.get("referenceHex")

        logger.info(f"Processing analysis {analysis_id} (job {job_id})...")
        try:
            suspect_bytes = bytes.fromhex(suspect_hex)
            reference_bytes = bytes.fromhex(reference_hex) if reference_hex else None

            # Run complete unified forensic pipeline
            result = run_unified_analysis(
                suspect_bytes,
                reference_bytes=reference_bytes,
                params=job.get("params"),
            )
            result["analysisId"] = analysis_id
            self.complete_job_to_api(job_id, analysis_id, result)
            logger.info(f"Completed analysis {analysis_id}: verdict={result['verdict']}")
        except Exception as e:
            logger.error(f"Failed to process analysis {analysis_id}: {e}", exc_info=True)

    def run_loop(self):
        """Main worker execution loop."""
        logger.info(f"Forensics Worker '{self.worker_id}' started. Polling {self.api_url} every {self.poll_interval}s...")
        while self.running:
            try:
                job = self.claim_job_from_api()
                if job:
                    self.process_job(job)
                else:
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(self.poll_interval)

        logger.info(f"Forensics Worker '{self.worker_id}' gracefully stopped.")


if __name__ == "__main__":
    worker = ForensicsWorker()
    worker.run_loop()

