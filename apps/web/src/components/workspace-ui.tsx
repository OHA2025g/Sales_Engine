"use client";

import { cn } from "@/lib/cn";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { Button } from "@/components/ui";

export function MetricStrip({
  items,
}: {
  items: { label: string; value: string; hint?: string }[];
}) {
  return (
    <div className="stats">
      {items.map((item) => (
        <div className="stat" key={item.label}>
          <div className="stat-name">{item.label}</div>
          <div className="stat-value num">{item.value}</div>
          {item.hint ? <div className="stat-note">{item.hint}</div> : null}
        </div>
      ))}
    </div>
  );
}

const PILL = {
  success: "good",
  review: "warn",
  blocked: "bad",
  info: "info",
  neutral: "",
} as const;

export type PillTone = keyof typeof PILL;

export function StatusPill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return <span className={cn("tag", PILL[tone])}>{children}</span>;
}

export function RecordAvatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
  return (
    <span className="avatar">{initials || "•"}</span>
  );
}

export function StageRail({ stages, current }: { stages: string[]; current: string }) {
  const index = Math.max(0, stages.indexOf(current));
  return (
    <ol className="mb-6 grid gap-2 md:grid-cols-6">
      {stages.map((stage, position) => (
        <li
          key={stage}
          className={cn(
            "rounded-md border px-3 py-2 text-xs",
            position === index ? "border-azure-600 bg-raised text-ink" : "border-[var(--line)] text-[var(--muted)]",
            position < index ? "text-[#8DD6B7]" : "",
          )}
        >
          {stage}
        </li>
      ))}
    </ol>
  );
}

export function EvidenceList({
  items,
}: {
  items: { label: string; ready: boolean; detail: string }[];
}) {
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.label} className="flex items-start justify-between gap-3 rounded-md border border-[var(--line)] bg-[#101722] px-3 py-2">
          <div>
            <p className="text-sm text-ink">{item.label}</p>
            <p className="text-xs text-[var(--muted)]">{item.detail}</p>
          </div>
          <StatusPill tone={item.ready ? "success" : "review"}>{item.ready ? "Recorded" : "Missing"}</StatusPill>
        </li>
      ))}
    </ul>
  );
}

export function SectionCard({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {action}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  pending,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  pending?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div className="modal" role="dialog" aria-modal="true">
      <button className="modal-scrim" aria-label="Close" onClick={onCancel} />
      <div className="modal-card">
        <header className="modal-head">
          <h2>{title}</h2>
        </header>
        <div className="modal-body">
          <p>{body}</p>
        </div>
        <footer className="modal-foot">
          <Button variant="line" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={pending}>
            {confirmLabel}
          </Button>
        </footer>
      </div>
    </div>
  );
}
