export function KpiCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="panel p-5">
      <p className="text-sm text-[var(--muted)]">{label}</p>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-ink tabular-nums">{value}</p>
      {hint ? <p className="mt-1.5 text-xs text-[var(--muted)]">{hint}</p> : null}
    </div>
  );
}
