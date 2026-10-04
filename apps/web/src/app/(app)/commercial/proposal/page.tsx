"use client";

import { DataTable } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Quote } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

export default function ProposalPage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["quotes"],
    queryFn: async () => (await api<Quote[]>("/api/v1/lifecycle/quotes")).data ?? [],
    enabled: can("commercial.read"),
  });
  if (!can("commercial.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading proposals" />;
  if (query.isError) return <ErrorState message="Quotes could not be loaded." />;
  const rows = (query.data ?? []).filter((row) => row.status !== "accepted");
  return (
    <div>
      <PageHeader
        eyebrow="Commercial"
        title="Proposal"
        subtitle="A proposal is the quote still in play. Accepted business is listed on contracts, not here."
        nextHref="/commercial/contracts"
        nextLabel="Contracts"
      />
      {rows.length === 0 ? (
        <EmptyState title="No open proposals" body="Create a quote before there is a proposal to review." />
      ) : (
        <DataTable
          rows={rows}
          href={(row) => `/commercial/quotes/${row.id}`}
          columns={[
            { key: "id", header: "Quote", cell: (row) => <Link href={`/commercial/quotes/${row.id}`}>{row.id.slice(0, 8)}</Link> },
            { key: "status", header: "State", cell: (row) => row.status },
            { key: "total", header: "Total", cell: (row) => money(row.total) },
          ]}
        />
      )}
    </div>
  );
}
