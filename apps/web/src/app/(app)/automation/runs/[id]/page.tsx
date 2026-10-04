"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { when } from "@/lib/format";
import type { AutonomyRun } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";

function tone(status: string): "success" | "blocked" | "review" | "info" {
  if (status === "completed" || status === "succeeded") return "success";
  if (status === "failed" || status === "blocked") return "blocked";
  if (status === "running") return "info";
  return "review";
}

export default function RunInspectorPage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["autonomy-run", params.id],
    queryFn: async () => (await api<AutonomyRun>(`/api/v1/autonomy/runs/${params.id}`)).data,
    enabled: can("autonomy.read"),
  });
  if (!can("autonomy.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the run" />;
  if (query.isError || !query.data) return <ErrorState message="This run is not in the tenant." />;
  const run = query.data;
  return (
    <div>
      <PageHeader
        eyebrow="Autopilot"
        title="Run inspector"
        subtitle={`${run.trigger} · started ${when(run.created_at)}`}
        nextHref="/automation/approvals"
        nextLabel="Decision inbox"
      />
      <div className="mb-4">
        <StatusPill tone={tone(run.status)}>{run.status}</StatusPill>
      </div>
      <p className="mb-4 text-sm text-[var(--muted)]">{run.summary || "No summary recorded."}</p>
      <ol className="space-y-2">
        {(run.steps ?? []).map((step) => (
          <li key={step.id} className="panel flex items-start justify-between gap-3 p-4">
            <div>
              <p className="text-sm text-ink">{step.position}. {step.name}</p>
              <p className="mt-1 text-xs text-[var(--muted)]">{step.detail_json || "No step detail."}</p>
            </div>
            <StatusPill tone={tone(step.status)}>{step.status}</StatusPill>
          </li>
        ))}
      </ol>
    </div>
  );
}
