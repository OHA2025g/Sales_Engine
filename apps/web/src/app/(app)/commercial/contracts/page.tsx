"use client";

import { DataTable } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Customer } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

export default function ContractsPage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["customers"],
    queryFn: async () => (await api<Customer[]>("/api/v1/customers")).data ?? [],
    enabled: can("accounts.read"),
  });
  if (!can("commercial.read") && !can("accounts.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading contracts" />;
  if (query.isError) return <ErrorState message="Customer commitments could not be loaded." />;
  const rows = query.data ?? [];
  return (
    <div>
      <PageHeader
        eyebrow="Commercial"
        title="Contracts"
        subtitle="Recurring ARR is the commitment on the customer. A signed document is unavailable until one is stored."
        nextHref="/customers"
        nextLabel="Customers"
      />
      {rows.length === 0 ? (
        <EmptyState title="No contracts" body="Accepted business creates a customer. Until then this list stays empty." />
      ) : (
        <DataTable
          rows={rows}
          href={(row) => `/commercial/contracts/${row.id}`}
          columns={[
            { key: "name", header: "Customer", cell: (row) => <Link href={`/commercial/contracts/${row.id}`}>{row.account_name || row.id.slice(0, 8)}</Link> },
            { key: "arr", header: "Recurring ARR", cell: (row) => money(row.arr) },
            { key: "doc", header: "Document", cell: () => <StatusPill tone="neutral">Unavailable</StatusPill> },
          ]}
        />
      )}
    </div>
  );
}
