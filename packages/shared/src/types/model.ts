/**
 * ModelVersion domain types.
 *
 * Tracks which detector/model versions exist in the system. This allows
 * forensic reproducibility — every DetectorOutput references a version.
 */

export type ModelType =
  | 'CLASSIFIER'
  | 'SEGMENTER'
  | 'DETECTOR'
  | 'COMPARATOR'
  | 'CLASSICAL';

export type ModelStatus = 'DRAFT' | 'ACTIVE' | 'DEPRECATED';

export interface ModelVersionRecord {
  id: string;
  /** Human-readable name, e.g. "ai-generated-resnet50" */
  name: string;
  /** Version tag, e.g. "1.0.0" */
  version: string;
  type: ModelType;
  status: ModelStatus;
  category: string;
  /** Storage path to the model artifact, when applicable */
  artifactStoragePath: string | null;
  /** SHA-256 of the model artifact, when applicable */
  sha256: string | null;
  description: string | null;
  createdAt: string;
  updatedAt: string;
}
