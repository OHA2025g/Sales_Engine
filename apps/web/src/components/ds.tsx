import { Icon } from "@/components/icon";
import Link from "next/link";
import type { ReactNode } from "react";

export function Notice({
  title,
  body,
  kind = "",
}: {
  title: string;
  body?: string;
  kind?: "" | "warn" | "good";
}) {
  const icon = kind === "warn" ? "alert" : kind === "good" ? "check" : "spark";
  return (
    <div className={`callout ${kind}`}>
      <Icon name={icon} />
      <div>
        <strong>{title}</strong>
        {body ? <p>{body}</p> : null}
      </div>
    </div>
  );
}

export function Stats({ items }: { items: { name: string; value: string; note?: string }[] }) {
  return (
    <div className="stats">
      {items.map((item) => (
        <div className="stat" key={item.name}>
          <div className="stat-name">{item.name}</div>
          <div className="stat-value num">{item.value}</div>
          {item.note ? <div className="stat-note">{item.note}</div> : null}
        </div>
      ))}
    </div>
  );
}

export function Panel({
  title,
  extra,
  children,
  body = true,
}: {
  title: string;
  extra?: ReactNode;
  children: ReactNode;
  body?: boolean;
}) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {extra}
      </header>
      {body ? <div className="panel-body">{children}</div> : children}
    </section>
  );
}

export function Line({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="line-item">
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function Checks({ items }: { items: { label: string; ok: boolean }[] }) {
  return (
    <ul className="checklist">
      {items.map((item) => (
        <li key={item.label}>
          <Icon name={item.ok ? "check" : "clock"} className={item.ok ? undefined : "wait"} />
          <span>{item.label}</span>
        </li>
      ))}
    </ul>
  );
}

export function Go({ href, children, primary = false }: { href: string; children: ReactNode; primary?: boolean }) {
  return (
    <Link className={primary ? "btn primary" : "btn"} href={href}>
      {children}
    </Link>
  );
}

export function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() ?? "")
      .join("") || "•"
  );
}
