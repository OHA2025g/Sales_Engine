"use client";

import { cn } from "@/lib/cn";
import { useEffect, useId } from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "line" }) {
  const styles = {
    primary: "primary",
    ghost: "ghost",
    line: "",
  }[variant];
  return (
    <button
      className={cn("btn", styles, className)}
      {...props}
    />
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "input",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "input",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "input",
        className,
      )}
      {...props}
    />
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "gold" | "mint" | "rose" | "ok" | "blue";
}) {
  const tones = {
    neutral: "",
    gold: "warn",
    mint: "good",
    rose: "bad",
    ok: "good",
    blue: "info",
  };
  return <span className={cn("tag", tones[tone])}>{children}</span>;
}

export function Score({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-[var(--muted)]">—</span>;
  const tone = value >= 70 ? "ok" : value >= 45 ? "gold" : "rose";
  return <Badge tone={tone}>{value}</Badge>;
}

export function Drawer({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button type="button" className="modal-scrim" aria-label="Close" onClick={onClose} />
      <div
        className="modal-card"
        style={{ maxHeight: "min(760px, calc(100vh - 48px))", overflow: "auto" }}
      >
        <header className="modal-head">
          <h2 id={titleId}>{title}</h2>
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export function FormActions({
  pending,
  onCancel,
  label = "Save",
}: {
  pending?: boolean;
  onCancel: () => void;
  label?: string;
}) {
  return (
    <div className="mt-8 flex justify-end gap-2">
      <Button type="button" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
      <Button type="submit" disabled={pending}>
        {pending ? "Saving…" : label}
      </Button>
    </div>
  );
}

export function CheckField({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" className="accent-[var(--brand)]" {...props} />
      {label}
    </label>
  );
}
