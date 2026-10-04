"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { labelize } from "@/lib/format";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";

type Step = { id: string; position: number; delay_days: number; action_type: string; template: string };
type SequenceDetail = { id: string; name: string; channel: string; status: string; purpose: string; steps: Step[] };

export default function SequenceDetailPage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["sequence", params.id],
    queryFn: async () => (await api<SequenceDetail>(`/api/v1/lifecycle/sequences/${params.id}`)).data,
    enabled: can("sequences.read"),
  });
  const activate = useMutation({
    mutationFn: () => api(`/api/v1/workflow/sequences/${params.id}/activate`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["sequence", params.id] }),
  });
  if (!can("sequences.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the sequence" />;
  if (query.isError || !query.data) return <ErrorState message="This sequence is not in the tenant." />;
  const row = query.data;
  return (
    <div>
      <PageHeader
        eyebrow="Sales"
        title={row.name}
        subtitle={`${labelize(row.channel)} · ${labelize(row.purpose)}. A draft cannot run.`}
        nextHref="/conversations"
        nextLabel="Conversations"
        actions={
          can("sequences.write") && row.status === "draft" ? (
            <Button onClick={() => activate.mutate()} disabled={activate.isPending}>Activate</Button>
          ) : null
        }
      />
      {activate.isError ? <p className="mb-4 text-sm text-[var(--rose)]">{(activate.error as Error).message}</p> : null}
      <ol className="space-y-3">
        {(row.steps ?? []).map((step) => (
          <li key={step.id} className="panel p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">Step {step.position}</p>
              <StatusPill tone="info">{labelize(step.action_type)} · day {step.delay_days}</StatusPill>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--muted)]">{step.template || "No template recorded."}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
