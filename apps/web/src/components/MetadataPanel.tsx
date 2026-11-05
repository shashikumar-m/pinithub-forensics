import type { ImageMetadataRecord } from '@pinithub/shared';

interface Props {
  metadata?: ImageMetadataRecord | null;
  /** Whether metadata extraction has been run but returned nothing */
  notExtracted?: boolean;
  loading?: boolean;
}

/**
 * MetadataPanel — displays real extracted metadata.
 *
 * Shows only real backend data. Missing fields show "—" not fake values.
 * GPS is shown as "Present (display controlled)" — never exposed raw by default.
 * Clearly notes that metadata is EVIDENCE, not proof of authenticity.
 */
export default function MetadataPanel({ metadata, notExtracted, loading }: Props) {
  if (loading) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">Metadata</h3>
        <p className="mt-2 text-sm text-slate-400">Extracting metadata…</p>
      </div>
    );
  }

  if (notExtracted || !metadata) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">Metadata</h3>
        <p className="mt-2 text-sm text-slate-400">
          Metadata not yet extracted. It will be available after image protection completes.
        </p>
        <p className="mt-1 text-xs text-amber-600">
          Manipulation detection: NOT_RUN
        </p>
      </div>
    );
  }

  const { camera, timestamps, location, c2pa } = {
    camera: {
      make: metadata.cameraMake,
      model: metadata.cameraModel,
      lensMake: metadata.lensMake,
      lensModel: metadata.lensModel,
      focalLength: metadata.focalLength,
      aperture: metadata.aperture,
      shutterSpeed: metadata.shutterSpeed,
      iso: metadata.iso,
    },
    timestamps: {
      capturedAt: metadata.capturedAt,
      capturedAtTimezone: metadata.capturedAtTimezone,
      metadataCreatedAt: metadata.metadataCreatedAt,
      metadataModifiedAt: metadata.metadataModifiedAt,
    },
    location: {
      hasGps: metadata.hasGps,
    },
    c2pa: {
      status: metadata.c2paStatus,
    },
  };

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Metadata</h3>
        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
          Extracted
        </span>
      </div>

      <p className="text-xs text-slate-400 italic">
        Metadata is forensic evidence, not proof of authenticity.
        Manipulation detection: NOT_RUN.
      </p>

      {/* Camera */}
      {(camera.make || camera.model) && (
        <Section title="Camera">
          <Row label="Make" value={camera.make} />
          <Row label="Model" value={camera.model} />
          <Row label="Lens" value={[camera.lensMake, camera.lensModel].filter(Boolean).join(' ') || null} />
          <Row label="Focal length" value={camera.focalLength ? `${camera.focalLength}mm` : null} />
          <Row label="Aperture" value={camera.aperture ? `f/${camera.aperture}` : null} />
          <Row label="Shutter" value={camera.shutterSpeed} />
          <Row label="ISO" value={camera.iso !== null && camera.iso !== undefined ? String(camera.iso) : null} />
        </Section>
      )}

      {/* Timestamps */}
      <Section title="Timestamps">
        <Row
          label="Captured"
          value={timestamps.capturedAt
            ? `${new Date(timestamps.capturedAt).toLocaleString()}${timestamps.capturedAtTimezone ? ` (${timestamps.capturedAtTimezone})` : ' (timezone unknown)'}`
            : null}
        />
        <Row
          label="Metadata modified"
          value={timestamps.metadataModifiedAt
            ? new Date(timestamps.metadataModifiedAt).toLocaleString()
            : null}
        />
      </Section>

      {/* Software */}
      {(metadata.software || metadata.editingSoftware) && (
        <Section title="Software">
          <Row label="Software" value={metadata.software} />
          {metadata.editingSoftware && (
            <div className="flex justify-between py-1">
              <dt className="text-slate-500">Editing software</dt>
              <dd className="flex items-center gap-1 text-right font-medium text-amber-700">
                {metadata.editingSoftware}
                <span title="Software evidence present — not a manipulation verdict">ⓘ</span>
              </dd>
            </div>
          )}
        </Section>
      )}

      {/* Location */}
      <Section title="Location">
        <Row
          label="GPS"
          value={location.hasGps ? 'Present (display controlled)' : 'Not detected'}
        />
      </Section>

      {/* C2PA */}
      <Section title="Content Credentials (C2PA)">
        <C2PABadge status={c2pa.status} />
      </Section>

      {/* Extractor info */}
      <p className="text-xs text-slate-400">
        Extracted by {metadata.extractorName} v{metadata.extractorVersion}
        {metadata.extractedAt ? ` · ${new Date(metadata.extractedAt).toLocaleString()}` : ''}
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{title}</p>
      <dl className="space-y-0.5 text-sm">{children}</dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex justify-between py-0.5">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800">{value ?? '—'}</dd>
    </div>
  );
}

function C2PABadge({ status }: { status: string | null }) {
  const map: Record<string, { label: string; color: string }> = {
    PRESENT: { label: 'Present', color: 'bg-blue-100 text-blue-700' },
    ABSENT: { label: 'Not detected', color: 'bg-slate-100 text-slate-500' },
    UNREADABLE: { label: 'Unreadable', color: 'bg-amber-100 text-amber-700' },
    UNSUPPORTED: { label: 'Unsupported', color: 'bg-slate-100 text-slate-400' },
  };
  const s = status ?? 'ABSENT';
  const { label, color } = map[s] ?? { label: s, color: 'bg-slate-100 text-slate-500' };
  return (
    <div className="flex justify-between py-0.5">
      <dt className="text-slate-500">C2PA / Content Credentials</dt>
      <dd>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>{label}</span>
      </dd>
    </div>
  );
}
