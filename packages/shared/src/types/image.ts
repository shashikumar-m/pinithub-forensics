/**
 * Image domain types.
 *
 * An Image record represents a stored image's metadata and references
 * to its object-storage location. The binary itself is NEVER stored in
 * the database — only the storage path, hash, and metadata.
 */

/** Role of an image within the forensic workflow. */
export type ImageRole = 'ORIGINAL' | 'SUSPECT' | 'DATASET';

/** Source of an image — camera capture or file upload */
export type ImageSource = 'CAMERA_CAPTURE' | 'FILE_UPLOAD';

/** Status of an image record — lifecycle states */
export type ImageStatus = 'RECEIVING' | 'VALIDATING' | 'PROTECTED' | 'FAILED' | 'DELETED';

export interface ImageRecord {
  id: string;
  /** Owner / creator identifier */
  ownerId: string;
  role: ImageRole;
  status: ImageStatus;
  source: ImageSource;
  /** Original filename as uploaded (sanitized, not used as storage key) */
  originalFilename: string;
  /** MIME type reported by the upload, validated server-side */
  mimeType: string;
  /** Format detected from file signature, e.g. "jpeg", "png", "webp" */
  format: string | null;
  /** Size in bytes */
  sizeBytes: number;
  /** SHA-256 hash of the stored original file bytes */
  sha256: string;
  /** Owner-scoped storage path inside the originals bucket */
  storagePath: string;
  /** Pixel width if known */
  width: number | null;
  /** Pixel height if known */
  height: number | null;
  /** width × height, stored for convenience */
  pixelCount: number | null;
  /** Color mode, e.g. "sRGB", "RGB", "RGBA" */
  colorMode: string | null;
  /** Timestamp of camera capture, when source is CAMERA_CAPTURE */
  captureTimestamp: string | null;
  /** Optional link to a dataset item */
  datasetItemId: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Payload accepted by POST /v1/uploads */
export interface UploadImageRequest {
  /** Role to assign to the uploaded image */
  role: ImageRole;
  /** How the image entered the system */
  source: ImageSource;
  /** Optional dataset item association */
  datasetItemId?: string;
  /** Capture timestamp (ISO string) for camera captures */
  captureTimestamp?: string;
}

/** Response from POST /v1/uploads */
export interface UploadImageResponse {
  image: ImageRecord;
  /** Pre-signed upload URL when using direct-to-storage upload flow */
  uploadUrl?: string;
  /** Whether this was a duplicate of an existing protected image */
  duplicate: boolean;
  /** Existing image ID when duplicate is true */
  existingImageId?: string;
}

/** Payload for recording consent */
export interface ConsentRequest {
  sourceType: ImageSource;
  consentVersion: string;
  policyVersion?: string;
}

/** Response from POST /v1/consents */
export interface ConsentResponse {
  consent: {
    id: string;
    consentGiven: boolean;
    consentVersion: string;
    timestamp: string;
  };
}
