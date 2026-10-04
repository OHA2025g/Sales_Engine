"use client";

import { PageHeader } from "@/components/page-header";
import { PAGES } from "@/lib/navigation";
import Link from "next/link";

export default function ScreenIndexPage() {
  const groups = PAGES.reduce<Record<string, typeof PAGES>>((acc, page) => {
    acc[page.workspace] = [...(acc[page.workspace] ?? []), page];
    return acc;
  }, {});
  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="All page designs"
        subtitle="Every workspace route in this app. Record screens open from the lists."
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(groups).map(([workspace, pages]) => (
          <section key={workspace} className="panel p-4">
            <h2 className="mb-3 text-sm font-semibold">{workspace}</h2>
            <ul className="space-y-1 text-sm">
              {pages.map((page) => (
                <li key={page.href}>
                  <Link href={page.href} className="text-[var(--muted)] hover:text-ink">{page.label}</Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
