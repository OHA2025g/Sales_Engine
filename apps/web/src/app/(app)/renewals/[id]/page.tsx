"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { EvidenceList, StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { money, when } from "@/lib/format";
import type { RenewalRow } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

export default function RenewalPlanPage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["renewals"],
    queryFn: async () => (await api<RenewalRow[]>("/api/v1/lifecycle/renewals")).data ?? [],
    enabled: can("success.read"),
  });
  if (!can("success.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the renewal" />;
  if (query.isError) return <ErrorState message="Renewals could not be loaded." />;
  const row = (query.data ?? []).find((item) => item.id === params.id);
  if (!row) return <ErrorState message="This renewal is not in the tenant." />;
  return (
    <div>
      <PageHeader
        eyebrow="Customers"
        title={row.account_name || "Renewal plan"}
        subtitle={`${money(row.current_arr)} · ${when(row.renewal_date)}`}
        nextHref="/expansion"
        nextLabel="Expansion"
      />
      <div className="mb-4">
        <StatusPill tone={row.stage === "at_risk" ? "blocked" : "review"}>{row.stage || row.status}</StatusPill>
      </div>
      <div className="panel p-5">
        <p className="mb-3 text-sm text-[var(--muted)]">{row.recommended_action || "No recommended action recorded."}</p>
        <EvidenceList
          items={[
            { label: "Why ready", ready: (row.why_ready ?? []).length > 0, detail: (row.why_ready ?? []).join("; ") || "No ready evidence." },
            { label: "Why at risk", ready: (row.why_at_risk ?? []).length === 0, detail: (row.why_at_risk ?? []).join("; ") || "No risk evidence." },
            { label: "Baseline", ready: row.baseline_amount != null, detail: row.baseline_amount == null ? row.baseline_status || "Unavailable" : money(row.baseline_amount) },
          ]}
        />
      </div>
    </div>
  );
}
