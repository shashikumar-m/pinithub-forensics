/**
 * AuditEvent domain types.
 *
 * AuditEvents form a tamper-evident audit trail. In later phases these
 * are chained / sealed so that any modification is detectable.
 */

export type AuditEventType =
  | 'IMAGE_UPLOADED'
  | 'ANALYSIS_CREATED'
  | 'JOB_QUEUED'
  | 'JOB_CLAIMED'
  | 'JOB_COMPLETED'
  | 'JOB_FAILED'
  | 'RECORD_SEALED'
  | 'RECORD_ACCESSED'
  | 'RECORD_DELETED'
  | 'REPORT_GENERATED';

export interface AuditEventRecord {
  id: string;
  eventType: AuditEventType;
  /** Actor / user who triggered the event */
  actorId: string | null;
  /** Resource affected, e.g. analysis ID */
  resourceId: string | null;
  /** Resource type, e.g. "analysis" */
  resourceType: string | null;
  /** Structured event payload */
  payload: Record<string, unknown>;
  /** Hash of the previous audit event for chain integrity (later phase) */
  previousHash: string | null;
  /** Hash of this event (later phase) */
  hash: string | null;
  createdAt: string;
}
