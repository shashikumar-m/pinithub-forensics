import { useState } from 'react';
import { useImages, useImage, useDeleteImage } from '../api/images';
import MetadataPanel from '../components/MetadataPanel';

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export default function Vault() {
  const { data, isLoading, error } = useImages(1, 20);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const deleteImage = useDeleteImage();

  function handleDelete(id: string, filename: string) {
    if (!window.confirm(`Delete "${filename}" from the vault? This cannot be undone.`)) return;
    deleteImage.mutate(id, {
      onSuccess: () => {
        if (selectedId === id) setSelectedId(null);
      },
    });
  }

  return (
    <div className="container-page font-sans">
      <h1 className="text-2xl font-bold font-mono text-slate-100">SEALED FORENSIC VAULT</h1>
      <p className="mt-1 text-sm font-mono text-slate-400">Protected original images and their cryptographic audit records.</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {/* Image list */}
        <div className="lg:col-span-1">
          {isLoading && <p className="text-sm font-mono text-cyan-400">Loading vault records…</p>}
          {error && <p className="text-sm font-mono text-red-400">Failed to load. Is the API running?</p>}
          {data?.items.length === 0 && (
            <div className="card text-center">
              <p className="text-sm font-mono text-slate-400">No protected images in vault yet.</p>
            </div>
          )}
          <ul className="space-y-2">
            {data?.items.map((img) => (
              <li key={img.id}>
                <div
                  className={`rounded-xl border p-3 transition-colors ${selectedId === img.id ? 'border-cyan-500/60 bg-cyan-950/40 shadow-[0_0_12px_rgba(6,182,212,0.2)]' : 'border-slate-800 bg-slate-900/80 hover:border-slate-700'}`}
                >
                  <button
                    className="w-full text-left"
                    onClick={() => setSelectedId(img.id)}
                  >
                    <p className="truncate text-sm font-mono font-medium text-slate-200">{img.originalFilename}</p>
                    <p className="mt-0.5 text-xs font-mono text-slate-400">
                      {img.format?.toUpperCase()} · {bytes(img.sizeBytes)}
                      {img.width && img.height ? ` · ${img.width}×${img.height}` : ''}
                    </p>
                    <p className="mt-0.5 text-xs font-mono text-slate-500">
                      {new Date(img.createdAt).toLocaleDateString()}
                    </p>
                  </button>
                  <button
                    className="mt-2 flex items-center gap-1 text-xs font-mono text-red-400 hover:text-red-300"
                    onClick={(e) => { e.stopPropagation(); handleDelete(img.id, img.originalFilename); }}
                    disabled={deleteImage.isPending}
                  >
                    🗑 Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Detail panel */}
        <div className="lg:col-span-2">
          {selectedId ? (
            <ImageDetail imageId={selectedId} />
          ) : (
            <div className="card flex h-40 items-center justify-center font-mono text-slate-400">
              <p className="text-sm">Select an image from the vault to view its forensic record</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ImageDetail({ imageId }: { imageId: string }) {
  const { data, isLoading } = useImage(imageId);

  if (isLoading) return <div className="card"><p className="text-sm text-slate-400">Loading…</p></div>;
  if (!data) return null;

  const { image } = data;
  const meta = image.metadata as any;

  return (
    <div className="space-y-4">
      {/* Basic info */}
      <div className="card space-y-2">
        <h2 className="font-semibold text-slate-900">{image.originalFilename}</h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <Row label="Format" value={image.format?.toUpperCase() ?? '—'} />
          <Row label="MIME" value={image.mimeType} />
          <Row label="Size" value={image.sizeBytes ? `${(Number(image.sizeBytes) / 1024).toFixed(1)} KB` : '—'} />
          <Row label="Dimensions" value={image.width && image.height ? `${image.width}×${image.height}` : '—'} />
          <Row label="Pixel count" value={image.pixelCount ? image.pixelCount.toLocaleString() : '—'} />
          <Row label="Source" value={image.source} />
          <Row label="Status" value={image.status} />
        </dl>
      </div>

      {/* SHA-256 */}
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">SHA-256</h3>
        <p className="mt-1 break-all font-mono text-xs text-slate-600">{image.sha256}</p>
        <IntegrityBadge imageId={imageId} />
      </div>

      {/* Metadata panel */}
      <MetadataPanel metadata={meta} notExtracted={!meta} />

      {/* Analysis status */}
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">Forensic Analysis</h3>
        <p className="mt-1 text-sm text-amber-700">Manipulation detection: <strong>NOT_RUN</strong></p>
        <p className="mt-1 text-xs text-slate-400">
          Forensic detectors (ELA, noise analysis, AI detection, etc.) are planned for later phases.
        </p>
      </div>
    </div>
  );
}

function IntegrityBadge({ imageId }: { imageId: string }) {
  const { data } = useImage(imageId);
  const check = (data?.image as any)?.latestIntegrityCheck;
  if (!check) return null;
  const ok = check.status === 'VERIFIED';
  return (
    <p className={`mt-1 text-xs font-medium ${ok ? 'text-green-600' : 'text-red-600'}`}>
      Hash integrity: {check.status}
    </p>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800">{value}</dd>
    </>
  );
}
