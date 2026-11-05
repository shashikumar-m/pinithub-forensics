interface Props {
  step: string;
}

const STEP_LABELS: Record<string, string> = {
  PROTECTING: 'Storing and hashing your image…',
  UPLOADING: 'Uploading…',
  CAPTURING: 'Camera ready',
  VALIDATING: 'Validating image…',
  QUEUED: 'Protection complete — analysis queued',
};

/**
 * ProgressState — shows an indeterminate spinner during async operations.
 * No fake percentage values. Step label comes from real workflow state.
 */
export default function ProgressState({ step }: Props) {
  const label = STEP_LABELS[step] ?? 'Processing…';
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600" />
      <p className="mt-4 text-sm text-slate-600">{label}</p>
    </div>
  );
}
