"use client";

import { Button, Input, Select } from "@/components/ui";
import type { ReactNode } from "react";

export function ListToolbar({
  query,
  onQuery,
  filter,
  onFilter,
  filterOptions,
  onCreate,
  createLabel,
  extra,
}: {
  query: string;
  onQuery: (value: string) => void;
  filter?: string;
  onFilter?: (value: string) => void;
  filterOptions?: { value: string; label: string }[];
  onCreate?: () => void;
  createLabel?: string;
  extra?: ReactNode;
}) {
  return (
    <div className="toolbar">
      <Input
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="Filter this list"
        className="max-w-sm"
      />
      {filterOptions && onFilter ? (
        <Select value={filter} onChange={(e) => onFilter(e.target.value)} className="max-w-[200px]">
          {filterOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      ) : null}
      <span className="ds-grow" />
      {extra}
      {onCreate ? <Button onClick={onCreate}>{createLabel ?? "Create"}</Button> : null}
    </div>
  );
}
