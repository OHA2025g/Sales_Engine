"use client";

import { cn } from "@/lib/cn";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

export type Column<T> = {
  key: string;
  header: string;
  className?: string;
  cell: (row: T) => ReactNode;
};

export function DataTable<T extends { id: string }>({
  columns,
  rows,
  href,
  bare = false,
}: {
  columns: Column<T>[];
  rows: T[];
  href?: (row: T) => string;
  bare?: boolean;
}) {
  const router = useRouter();
  const table = (
    <>
      <div className="table-wrap">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 border-b border-[var(--line)] bg-[#101722] text-xs font-semibold text-[var(--meta)]">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className={cn("px-4 py-2.5", column.className)}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  "border-t border-[var(--line)] transition hover:bg-raised",
                  href ? "cursor-pointer" : "",
                )}
                onClick={(event) => {
                  if (!href) return;
                  const target = event.target;
                  if (target instanceof HTMLElement && target.closest("button, a, input, select, textarea")) return;
                  router.push(href(row));
                }}
              >
                {columns.map((column) => (
                  <td key={column.key} className={cn("px-4 py-2.5 text-ink", column.className)}>
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {bare ? null : (
        <footer className="table-footer">
          <span>{rows.length} records</span>
          <span>Record selection opens the relevant workspace</span>
        </footer>
      )}
    </>
  );
  if (bare) return table;
  return <div className="panel">{table}</div>;
}
