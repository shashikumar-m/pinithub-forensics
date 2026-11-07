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
    <div className="container-page">
      <h1 className="text-2xl font-bold text-slate-900">Vault</h1>
      <p className="mt-1 text-sm text-slate-600">Protected original images and their forensic records.</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {/* Image list */}
        <div className="lg:col-span-1">
          {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
          {error && <p className="text-sm text-red-600">Failed to load. Is the API running?</p>}
          {data?.items.length === 0 && (
            <div className="card text-center">
              <p className="text-sm text-slate-400">No protected images yet.</p>
            </div>
          )}
          <ul className="space-y-2">
            {data?.items.map((img) => (
              <li key={img.id}>
                <div
                  className={`rounded-lg border p-3 transition-colors ${selectedId === img.id ? 'border-brand-500 bg-brand-50' : 'border-slate-200 bg-white'}`}
                >
                  <button
                    className="w-full text-left"
                    onClick={() => setSelectedId(img.id)}
                  >
                    <p className="truncate text-sm font-medium text-slate-800">{img.originalFilename}</p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {img.format?.toUpperCase()} · {bytes(img.sizeBytes)}
                      {img.width && img.height ? ` · ${img.width}×${img.height}` : ''}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {new Date(img.createdAt).toLocaleDateString()}
                    </p>
                  </button>
                  <button
                    className="mt-2 flex items-center gap-1 text-xs text-red-500 hover:text-red-700"
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
            <div className="card flex h-40 items-center justify-center">
              <p className="text-sm text-slate-400">Select an image to view its forensic record</p>
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
