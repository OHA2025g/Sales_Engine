import { cn } from "@/lib/cn";

const ICONS: Record<string, string> = {
  dashboard: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  compass: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M16 8l-3 5-5 3 3-5z",
  megaphone: "M3 10v4h4l12 5V5L7 10z M7 14l2 7h3l-2-6 M22 9v6",
  briefcase: "M8 7V4h8v3 M3 7h18v14H3z M3 12h18 M10 11v4h4v-4",
  document: "M14 2H5v20h14V7z M14 2v5h5 M8 12h8 M8 16h6",
  heart: "M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8",
  workflow: "M3 3h6v6H3z M15 15h6v6h-6z M3 15h6v6H3z M6 9v6 M9 6h9v9",
  chart: "M3 3v18h18 M7 16v-4 M12 16V8 M17 16V5",
  settings: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z",
  search: "M21 21l-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  chevron: "M9 5l7 7-7 7",
  bell: "M6 8a6 6 0 0 1 12 0v7l3 3H3l3-3z M10 21h4",
  spark: "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  shield: "M12 2l9 4v6c0 6-9 10-9 10S3 18 3 12V6z M8 12l3 3 5-6",
  alert: "M12 3l10 18H2z M12 9v5 M12 17v.2",
  check: "M5 12l4 4L19 6",
  clock: "M12 7v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  file: "M14 2H5v20h14V7z M14 2v5h5",
  mail: "M4 6h16v12H4z M4 7l8 6 8-6",
  link: "M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1 M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1",
};

export function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <svg className={cn("icon", className)} viewBox="0 0 24 24" aria-hidden="true">
      <path d={ICONS[name] ?? ICONS.document} />
    </svg>
  );
}
