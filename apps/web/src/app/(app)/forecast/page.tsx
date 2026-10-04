"use client";

import { DataTable } from "@/components/data-table";
import { Go, Panel, Stats } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { money, pct } from "@/lib/format";
import type { Forecast } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export default function ForecastPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["forecast"],
    queryFn: async () => (await api<Forecast[]>("/api/v1/lifecycle/forecast")).data ?? [],
    enabled: can("forecast.read"),
  });
  const refresh = useMutation({
    mutationFn: () => api("/api/v1/lifecycle/forecast/refresh", { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["forecast"] }),
  });

  if (!can("forecast.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Reading snapshots" />;
  if (query.isError) return <ErrorState message="Forecast could not be assembled." />;
  const rows = query.data ?? [];
  const latest = rows[0];

  return (
    <div>
      <PageHeader
        eyebrow="Phase 15"
        title="Forecast"
        subtitle="Committed, pipeline, and weighted values come from open opportunities. Win rate is won / decided. Not ML."
        actions={<Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>Snapshot now</Button>}
      />
      <Stats
        items={[
          { name: "Commit forecast", value: latest ? money(latest.committed) : "—", note: latest?.period || "No snapshot yet" },
          { name: "Best-case pipeline", value: latest ? money(latest.pipeline) : "—", note: "Qualified period opportunities" },
          { name: "Weighted forecast", value: latest ? money(latest.weighted) : "—", note: "Explicit rules · not trained ML" },
          { name: "Win rate", value: latest ? pct(latest.win_rate) : "—", note: "Won divided by decided" },
        ]}
      />
      <div className="ds-grid wide section-gap">
        <Panel title="Period snapshots" extra={<Go href="/pipeline">Inspect contributing pipeline</Go>} body={false}>
          {rows.length === 0 ? (
            <div className="empty"><h3>No snapshots</h3><p>Take a snapshot. The API will not invent coverage.</p></div>
          ) : (
            <DataTable
              bare
              rows={rows}
              columns={[
                { key: "period", header: "Period", cell: (row) => row.period },
                { key: "committed", header: "Committed", cell: (row) => money(row.committed) },
                { key: "weighted", header: "Weighted", cell: (row) => money(row.weighted) },
                { key: "win", header: "Win rate", cell: (row) => pct(row.win_rate) },
                { key: "ver", header: "Version", cell: (row) => <Badge>{row.version}</Badge> },
              ]}
            />
          )}
        </Panel>
        <Panel title="How this forecast is built">
          <p className="small muted">Each total reconciles to opportunities in the selected period. Stage totals are aggregated, not overwritten. Accepted business stays separate from pipeline.</p>
        </Panel>
      </div>
    </div>
  );
}
