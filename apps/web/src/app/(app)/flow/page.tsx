"use client";

import { Icon } from "@/components/icon";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { useAuth } from "@/lib/auth";
import type { Overview } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

const PHASES = [
  ["01 · Plan & sense", "Choose where to compete", "Revenue target, offer, ICP, territory, and source evidence.", "Approved strategy and a relevant account hypothesis", "/strategy"],
  ["02 · Acquire & qualify", "Turn demand into eligible leads", "Campaigns, content, capture, duplicates, enrichment, and qualification.", "Eligible lead and an accountable owner", "/acquisition"],
  ["03 · Engage & convert", "Progress the conversation", "Activated sequences, reply handling, meetings, and a qualification outcome.", "Sales-qualified opportunity and an agreed next step", "/leads"],
  ["04 · Close", "Authorize and record the agreement", "Proposal, quote version, commercial decisions, acceptance, and contract.", "Accepted terms and a verified delivery handoff", "/commercial"],
  ["05 · Deliver & retain", "Make customer value observable", "Onboarding, activation, usage, support, health, value reviews, and renewal.", "Activated customer and renewal evidence", "/onboarding"],
  ["06 · Expand & improve", "Use evidence to grow", "Expansion, advocacy, attribution, cohorts, performance, and feedback.", "A justified opportunity and measured learning", "/expansion"],
] as const;

export default function FlowPage() {
  const { can } = useAuth();
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: async () => (await api<Overview>("/api/v1/command-center/overview")).data,
    enabled: can("command_center.read"),
  });
  const decisions = useQuery({
    queryKey: ["workflow-command"],
    queryFn: async () =>
      (await api<{ id: string; account: string; reason: string; kind: string }[]>("/api/v1/workflow/command")).data ?? [],
    enabled: can("command_center.read"),
  });
  if (!can("command_center.read")) return <DeniedState />;
  if (overview.isLoading) return <LoadingState label="Loading the revenue journey" />;
  if (overview.isError) return <ErrorState message="The journey could not be loaded." />;
  const exceptions = (decisions.data ?? []).filter((row) => row.kind === "exception");
  return (
    <div>
      <PageHeader
        eyebrow="Command Centre"
        title="Revenue journey"
        subtitle="Every handoff carries its evidence, owner, next due time, and recovery path."
        nextHref="/strategy"
        nextLabel="Revenue strategy"
      />
      <div className="callout">
        <Icon name="spark" />
        <div>
          <strong>Six stages, one operating path</strong>
          <p>{overview.data?.lifecycle?.note || "Counts stay with each workspace. A missing pulse stays unavailable."}</p>
        </div>
      </div>
      <div className="flowmap">
        {PHASES.map(([step, title, desc, handoff, href]) => (
          <section className="flow-phase" key={step}>
            <span className="upper">{step}</span>
            <h2>{title}</h2>
            <p>{desc}</p>
            <div className="next">
              <span className="muted">Handoff</span>
              <br />
              {handoff}
            </div>
            <Link className="btn" href={href}>Open workspace</Link>
          </section>
        ))}
      </div>
      <div className="section-gap">
        <section className="panel">
          <header className="panel-head">
            <h2>Owned exceptions</h2>
            <span className="tag warn">{exceptions.length}</span>
          </header>
          {exceptions.length === 0 ? (
            <div className="empty">
              <h3>No blocked journeys</h3>
              <p>An empty queue is not a health score. Exceptions appear here when a journey cannot progress.</p>
            </div>
          ) : (
            exceptions.map((row) => (
              <div className="row" key={row.id}>
                <span className="avatar square"><Icon name="alert" /></span>
                <div className="main">
                  <h3>{row.account || "Unnamed record"}</h3>
                  <p>{row.reason}</p>
                </div>
                <span className="tag bad">Blocked</span>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}
