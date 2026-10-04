"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Customer } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function ContractDetailPage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["customer", params.id],
    queryFn: async () => (await api<Customer>(`/api/v1/customers/${params.id}`)).data,
    enabled: can("accounts.read"),
  });
  if (!can("accounts.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the contract" />;
  if (query.isError || !query.data) return <ErrorState message="This customer is not in the tenant." />;
  const row = query.data;
  return (
    <div>
      <PageHeader
        eyebrow="Commercial"
        title={row.account_name || "Contract"}
        subtitle="Recurring revenue is taken from contract lines. One-time bookings are not ARR."
        nextHref="/onboarding"
        nextLabel="Onboarding"
      />
      <div className="panel max-w-xl space-y-3 p-5 text-sm">
        <p className="text-2xl font-semibold tabular-nums">{money(row.arr)}</p>
        <p className="text-[var(--muted)]">Status {row.status}</p>
        <StatusPill tone="neutral">Signed document unavailable</StatusPill>
      </div>
    </div>
  );
}
