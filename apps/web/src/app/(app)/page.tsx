"use client";

import { Icon } from "@/components/icon";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { ConfirmDialog } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { money, when } from "@/lib/format";
import { useRolePreview } from "@/lib/role-preview";
import type { AutonomyStatus, AutopilotSettings, Overview, Task } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

type Decision = {
  id: string;
  kind: string;
  account: string;
  reason: string;
  recommended_action: string;
  entity_type: string;
  entity_id: string;
};

const FLOW = [
  { name: "Acquire", field: "campaigns" as const, href: "/acquisition", note: "Eligible records" },
  { name: "Engage", field: "enrollments" as const, href: "/leads", note: "Active journeys" },
  { name: "Convert", field: "open_quotes" as const, href: "/pipeline", note: "Open quotes" },
  { name: "Deliver", field: "customers" as const, href: "/onboarding", note: "Customers in delivery" },
  { name: "Retain", field: "renewals_due_90" as const, href: "/renewals", note: "Renewals in 90 days" },
  { name: "Expand", field: "whitespace" as const, href: "/expansion", note: "Expansion evidence" },
];

function decisionHref(row: Decision): string {
  if (row.entity_type === "lead") return `/leads/${row.entity_id}`;
  if (row.entity_type === "opportunity") return `/opportunities/${row.entity_id}`;
  if (row.entity_type === "quote") return `/commercial/quotes/${row.entity_id}`;
  return "/automation/approvals";
}

function focusTitle(role: string) {
  if (role === "Customer success") return "Customer risk and activation";
  if (role === "Marketing manager") return "Campaign decisions and demand";
  if (role === "Sales development") return "Lead eligibility and engagement";
  if (role === "Account executive") return "Deal progression and commercial decisions";
  return "Decisions that move revenue";
}

export default function CommandCenterPage() {
  const { can } = useAuth();
  const { role } = useRolePreview();
  const client = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const query = useQuery({
    queryKey: ["overview"],
    queryFn: async () => (await api<Overview>("/api/v1/command-center/overview")).data,
    enabled: can("command_center.read"),
  });
  const autonomy = useQuery({
    queryKey: ["autonomy-status"],
    queryFn: async () => (await api<AutonomyStatus>("/api/v1/autonomy/status")).data,
    enabled: can("autonomy.read"),
  });
  const settings = useQuery({
    queryKey: ["autopilot-settings"],
    queryFn: async () => (await api<AutopilotSettings>("/api/v1/autonomy/settings")).data,
    enabled: can("autonomy.read"),
  });
  const decisions = useQuery({
    queryKey: ["workflow-command"],
    queryFn: async () => (await api<Decision[]>("/api/v1/workflow/command")).data ?? [],
    enabled: can("command_center.read"),
  });
  const pause = useMutation({
    mutationFn: (stopped: boolean) =>
      api("/api/v1/autonomy/settings", { method: "PATCH", body: JSON.stringify({ emergency_stop: stopped }) }),
    onSuccess: () => {
      setConfirm(false);
      void client.invalidateQueries({ queryKey: ["autopilot-settings"] });
    },
  });

  if (!can("command_center.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading the revenue workspace" />;
  if (query.isError || !query.data) return <ErrorState message="The command centre could not be loaded. Retry once the API is reachable." />;

  const k = query.data.kpis;
  const pulse = query.data.lifecycle;
  const rows = decisions.data ?? [];
  const manager = role === "Revenue manager" || role === "Marketing manager";
  const stopped = Boolean(settings.data?.emergency_stop);
  const tasks = query.data.overdue_tasks ?? [];
  const stats = manager
    ? [
        ["Qualified pipeline", money(k.weighted_pipeline_value), "Current tenant · weighted"],
        ["Accepted business", String(k.won_opportunities), "Won opportunities recorded"],
        ["Active journeys", String(pulse?.enrollments ?? 0), "Enrollments in this workspace"],
        ["Decisions due", String(rows.length || k.pending_approvals), "Assigned to accountable owners"],
      ]
    : [
        ["Assigned work", String(k.tasks_open), "Open tasks in this tenant"],
        ["Progressing", String(pulse?.enrollments ?? 0), "Journeys still moving"],
        ["Needs a decision", String(rows.length), "Reviewable exceptions"],
        ["Due today", String(k.tasks_overdue), "Owned next steps"],
      ];

  return (
    <div>
      <PageHeader
        eyebrow="Command Centre"
        title="Overview"
        subtitle="Supervise progress, decisions, and exceptions."
        actions={
          <>
            {can("autonomy.write") ? (
              <button className="btn" onClick={() => (stopped ? pause.mutate(false) : setConfirm(true))}>
                {stopped ? "Resume journeys" : "Pause journeys"}
              </button>
            ) : null}
            <Link className="btn primary" href="/automation/approvals">Review decisions</Link>
          </>
        }
      />
      {stopped ? (
        <div className="callout warn">
          <Icon name="alert" />
          <div>
            <strong>All journeys paused</strong>
            <p>Queued work remains visible. No execution progresses until the workspace is resumed.</p>
          </div>
        </div>
      ) : null}
      <div className="stats">
        {stats.map(([name, value, note]) => (
          <div className="stat" key={name}>
            <div className="stat-name">{name}</div>
            <div className="stat-value num">{stopped && name !== "Decisions due" ? "—" : value}</div>
            <div className="stat-note">{note}</div>
          </div>
        ))}
      </div>
      <div className="between" style={{ marginBottom: 14 }}>
        <h2>Revenue flow</h2>
        <Link className="btn" href="/flow">Inspect journey</Link>
      </div>
      <div className="journey-lanes">
        {FLOW.map((lane) => (
          <Link className="lane" href={lane.href} key={lane.name}>
            <div className="name">{lane.name}</div>
            <div className="total num">{stopped ? "—" : String(pulse ? pulse[lane.field] : "—")}</div>
            <div className="lane-note">{stopped ? "Paused" : lane.note}</div>
          </Link>
        ))}
      </div>
      <div className="ds-grid wide">
        <section className="panel">
          <header className="panel-head">
            <h2>{focusTitle(role)}</h2>
            <span className="tag warn">{rows.length} owned exceptions</span>
          </header>
          {rows.length === 0 ? (
            <div className="empty">
              <h3>No decisions waiting</h3>
              <p>Blocked journeys and waiting approvals appear here.</p>
            </div>
          ) : (
            rows.slice(0, 6).map((row) => (
              <div className="row" key={row.id}>
                <span className="avatar square"><Icon name={row.kind === "exception" ? "shield" : "heart"} /></span>
                <div className="main">
                  <span className="upper">{row.kind}</span>
                  <h3 style={{ marginTop: 5 }}>{/^[0-9a-f]{8}-/i.test(row.account) ? row.reason : row.account || row.reason}</h3>
                  <p>{/^[0-9a-f]{8}-/i.test(row.account) ? row.recommended_action : row.reason}</p>
                </div>
                <Link className="btn" href={decisionHref(row)}>Review</Link>
              </div>
            ))
          )}
        </section>
        <section className="panel">
          <header className="panel-head"><h2>Next expected outcomes</h2></header>
          <div className="timeline">
            {(tasks.length ? tasks.slice(0, 3) : []).map((task: Task) => (
              <div className="time-event" key={task.id}>
                <span className="time-dot" />
                <div>
                  <h3>{task.title}</h3>
                  <p>{task.description || "Owned next step"}</p>
                  <p>{when(task.due_at) || "Due date unavailable"}</p>
                </div>
              </div>
            ))}
            {tasks.length === 0 ? (
              <div className="time-event">
                <span className="time-dot" />
                <div>
                  <h3>No dated outcome</h3>
                  <p>Overdue tasks and meetings appear here when the tenant has them.</p>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </div>
      <div className="ds-grid section-gap">
        <section className="panel">
          <header className="panel-head"><h2>Revenue objective</h2></header>
          <div className="panel-body">
            <div className="between">
              <span className="muted small">Open pipeline {money(k.open_pipeline_value)}</span>
              <span className="tag">Target unavailable</span>
            </div>
            <div className="between" style={{ margin: "16px 0" }}>
              <h2>{money(k.weighted_pipeline_value)} weighted</h2>
              <span className="num muted">Win rate {Math.round(k.win_rate * 100)}%</span>
            </div>
            <div className="progress"><i style={{ width: "0%" }} /></div>
            <div className="ds-flex" style={{ marginTop: 18 }}>
              <Link className="btn" href="/strategy">View strategy</Link>
              <Link className="btn" href="/forecast">View forecast</Link>
            </div>
          </div>
        </section>
        <section className="panel">
          <header className="panel-head"><h2>Operating boundaries</h2></header>
          <div className="panel-body">
            <div className="line-item"><span>Autonomy mode</span><span>{autonomy.data?.enabled ? "Enabled" : "Unavailable"}</span></div>
            <div className="line-item"><span>External actions</span><span>Approval is not delivery</span></div>
            <div className="line-item"><span>Contact eligibility</span><span>Revalidated before execution</span></div>
            <div className="line-item"><span>Policy blocks</span><span>{autonomy.data?.blocked_policy ?? "—"}</span></div>
            <div style={{ marginTop: 15 }}><Link className="btn" href="/policies">Inspect policies</Link></div>
          </div>
        </section>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Pause every journey?"
        body="This stops social, ads, and sends across channels. Queued work stays visible until you resume."
        confirmLabel="Pause journeys"
        pending={pause.isPending}
        onCancel={() => setConfirm(false)}
        onConfirm={() => pause.mutate(true)}
      />
    </div>
  );
}
