/**
 * AnalysisJob domain types.
 *
 * An AnalysisJob represents a single unit of asynchronous work that the
 * Python forensic service executes. Jobs move through a lifecycle
 * (QUEUED -> RUNNING -> DONE/FAILED) and support safe concurrent
 * claiming via PostgreSQL row locking (SKIP LOCKED).
 */

export type JobStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED';

export interface AnalysisJobRecord {
  id: string;
  analysisId: string;
  status: JobStatus;
  /** Which detector pipeline this job runs */
  pipeline: string;
  /** Attempt counter for retry logic */
  attempt: number;
  /** Max attempts before the job is marked FAILED */
  maxAttempts: number;
  /** Worker identifier that claimed the job */
  claimedBy: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  /** Structured error info if FAILED */
  error: JobError | null;
}

export interface JobError {
  code: string;
  message: string;
  stack?: string;
}

/** Shape returned by the job-claim endpoint (Python worker polls API). */
export interface ClaimJobResponse {
  job: AnalysisJobRecord | null;
}

/** Shape used to update a job's result. */
export interface CompleteJobRequest {
  status: 'DONE' | 'FAILED';
  error?: JobError;
}
