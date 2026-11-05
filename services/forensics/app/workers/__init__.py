"""
Workers package — job processing for the forensic service.

Workers poll the Node API for queued analysis jobs, claim them using
SKIP LOCKED semantics, run the appropriate pipeline, and report
results back.

Phase 0: Placeholder. Worker logic will be implemented when detectors
are ready. The job-claim architecture is prepared in the Node API
(AnalysisService.claimNextJob uses FOR UPDATE SKIP LOCKED).
"""
