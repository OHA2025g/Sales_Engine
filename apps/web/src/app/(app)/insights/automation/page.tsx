"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { MetricStrip } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";

type Roi = {
  automation: { automated_internal_tasks: number; approval_actions: number; autonomous_execution_rate: number | null };
  pipeline: { ai_discovery_leads: number; all_leads: number };
};

export default function AutomationPerformancePage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["pilot-roi"],
    queryFn: async () => (await api<Roi>("/api/v1/pilot/roi")).data,
    enabled: can("pilot.view"),
  });
  if (!can("pilot.view")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading automation performance" />;
  if (query.isError || !query.data) return <ErrorState message="Automation performance could not be loaded." />;
  const data = query.data;
  const rate = data.automation.autonomous_execution_rate;
  return (
    <div>
      <PageHeader
        eyebrow="Insights"
        title="Automation performance"
        subtitle="Rates come from recorded tasks and approvals. A missing rate stays unavailable."
        nextHref="/forecast"
        nextLabel="Forecast"
      />
      <MetricStrip
        items={[
          { label: "Internal tasks", value: String(data.automation.automated_internal_tasks) },
          { label: "Approval actions", value: String(data.automation.approval_actions) },
          { label: "Autonomous rate", value: rate == null ? "Unavailable" : `${Math.round(rate * 100)}%` },
          { label: "Discovered leads", value: String(data.pipeline.ai_discovery_leads), hint: `${data.pipeline.all_leads} leads in total` },
        ]}
      />
    </div>
  );
}
