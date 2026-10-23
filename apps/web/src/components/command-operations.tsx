"use client";

import { ErrorState, LoadingState } from "@/components/states";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

type Journey = {
  journey_id: string;
  status: string;
  business_state: string;
  workflow: string;
  summary: string;
  lead_id: string;
  lead_email: string;
  next_action: string;
  waiting_reason: string;
};

type RunningStep = {
  step_id: string;
  journey_id: string;
  name: string;
  lease_owner: string;
  age_seconds: number | null;
  stale: boolean;
};

type Evidence = {
  kind: string;
  status: string;
  provider: string;
  provider_ref: string;
  excerpt: string;
};

type Prospect = { name: string; next_action: string; owner_name: string; explanation: string; outcome: string };
type PlanVersion = { id: string; version: number; status: string; channel: string; outcome: string };
type PlanProduct = { id: string; name: string; kind: string; list_price: string; currency: string };
type Operations = {
  offer: { name: string; offer_key: string; scope: string; sales_rules_configured: boolean } | null;
  journeys: Journey[];
  running_steps: RunningStep[];
  stale_leases: RunningStep[];
  queue_age_seconds: number | null;
  scheduler: { state?: string; scheduler_unhealthy?: boolean; last_beat_at?: string | null };
  worker?: { state?: string; scheduler_unhealthy?: boolean; last_beat_at?: string | null };
  held_external_work?: number;
  evidence: Evidence[];
  exceptions: { journey_id: string; status: string; waiting_reason: string; next_action: string }[];
  outcomes: Record<string, number>;
  discovery?: { status: string; reason: string; created: number; failures: string; prospects: Prospect[] };
  marketing?: {
    status: string;
    next_action: string;
    blocker: string;
    research_runs?: number;
    research_limit?: number;
    versions: PlanVersion[];
    products?: PlanProduct[];
    offer_name?: string;
    product_id?: string;
    outcomes: { attributed_enquiries: number; impressions: number | null; optimization: string };
  };
};

type Readiness = { channel: string; checks: { name: string; status: string; reason: string; href: string }[] };
type NextAction = {
  journey_id: string;
  job_id: string;
  state: string;
  next_action: string;
  waiting_reason: string;
  coverage_known: number;
  coverage_required: number;
  confidence: string;
  meeting_eligible: boolean;
  sales_qualified: boolean;
};
type Control = { journey_id: string; job_id: string; status: string; detail?: string };

function key() {
  return crypto.randomUUID();
}

export function CommandOperations() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [result, setResult] = useState("");
  const [journeyId, setJourneyId] = useState("");
  const [productId, setProductId] = useState("");
  const operations = useQuery({
    queryKey: ["command-operations"],
    queryFn: async () => (await api<Operations>("/api/v1/command-center/operations")).data,
    enabled: can("command_center.read"),
    refetchInterval: 4000,
  });
  const selected = journeyId || operations.data?.journeys[0]?.journey_id || "";

  const show = (text: string) => setResult(text);
  const fail = (error: unknown) => show(error instanceof Error ? error.message : "The action failed.");

  const readiness = useMutation({
    mutationFn: async () => (await api<Readiness>("/api/v1/operating-plans/readiness?channel=email")).data,
    onSuccess: (data) => {
      if (!data) return;
      show(data.checks.map((row) => `${row.name}: ${row.status}. ${row.reason}`).join(" "));
    },
    onError: fail,
  });
  const form = useMutation({
    mutationFn: async () => (await api<{ url: string }>("/api/v1/acquisition/interest-form")).data,
    onSuccess: (data) => {
      if (data?.url) {
        show(`Capture form: ${data.url}`);
        window.open(data.url, "_blank", "noopener,noreferrer");
      }
    },
    onError: fail,
  });
  const preview = useMutation({
    mutationFn: async (id: string) => (await api<NextAction>(`/api/v1/journeys/${id}/next-action`)).data,
    onSuccess: (data) => {
      if (!data) return;
      show(
        `Journey ${data.journey_id} job ${data.job_id} is ${data.state}. Next action: ${data.next_action || "none"}. ${data.waiting_reason} Coverage ${data.coverage_known}/${data.coverage_required}. Confidence ${data.confidence}. Meeting ${data.meeting_eligible ? "eligible" : "not eligible"}. Sales ${data.sales_qualified ? "qualified" : "not qualified"}.`,
      );
    },
    onError: fail,
  });
  const plan = useMutation({
    mutationFn: async (input: { path: string; method?: "GET" | "POST"; body?: unknown }) => {
      if ((input.method ?? "POST") === "GET") return api<Record<string, unknown>>(`/api/v1/operating-plans/${input.path}`);
      return api<Record<string, unknown>>(`/api/v1/operating-plans/${input.path}`, {
        method: "POST",
        headers: { "Idempotency-Key": key() },
        body: JSON.stringify(input.body ?? {}),
      });
    },
    onSuccess: (response) => {
      const data = response.data;
      const detail = data && typeof data.detail === "string" ? data.detail : "The operating plan action finished.";
      show(detail);
      void client.invalidateQueries({ queryKey: ["command-operations"] });
    },
    onError: fail,
  });
  const control = useMutation({
    mutationFn: async (input: { id: string; action: "pause" | "resume" | "cancel" | "continue" }) =>
      api<Control>(`/api/v1/journeys/${input.id}/${input.action}`, {
        method: "POST",
        headers: { "Idempotency-Key": key() },
        body: JSON.stringify({}),
      }),
    onSuccess: (response) => {
      const data = response.data;
      show(`Journey ${data?.journey_id} job ${data?.job_id} is ${data?.status}. ${data?.detail || ""}`);
      void client.invalidateQueries({ queryKey: ["command-operations"] });
    },
    onError: fail,
  });

  if (!can("command_center.read")) return <ErrorState message="You do not have permission to view live operations." />;
  if (operations.isLoading) return <LoadingState label="Loading live operations" />;
  if (operations.isError || !operations.data) return <ErrorState message="Live operations could not be loaded." />;
  const data = operations.data;
  const outcomes = Object.entries(data.outcomes);
  const pending = data.marketing?.versions?.find((row) => row.status === "draft");
  const authorized = data.marketing?.versions?.find((row) => row.status === "authorized");

  return (
    <section className="panel section-gap">
      <header className="panel-head">
        <h2>Live operations</h2>
        <span className="tag">{data.scheduler.state || "scheduler unknown"}</span>
      </header>
      <div className="panel-body">
        <div className="line-item">
          <span>Active offer</span>
          <span>
            {data.offer
              ? `${data.offer.name}${data.offer.scope ? ` · ${data.offer.scope}` : ""}${data.offer.sales_rules_configured ? " · sales rules configured" : " · sales rules not configured"}`
              : "No active offer is recorded"}
          </span>
        </div>
        <div className="line-item">
          <span>Scheduler</span>
          <span>
            {data.scheduler.state === "ok" ? "Healthy" : data.scheduler.state === "unhealthy" ? "Unhealthy" : "No heartbeat recorded"}
            {data.scheduler.last_beat_at ? ` · ${data.scheduler.last_beat_at}` : ""}
          </span>
        </div>
        <div className="line-item">
          <span>Worker</span>
          <span>
            {data.worker?.state === "ok" ? "Healthy" : data.worker?.state === "unhealthy" ? "Unhealthy" : "No worker heartbeat recorded"}
            {data.worker?.last_beat_at ? ` · ${data.worker.last_beat_at}` : ""}
          </span>
        </div>
        <div className="line-item">
          <span>Held external work</span>
          <span>{data.held_external_work ?? 0}</span>
        </div>
        <div className="line-item">
          <span>Oldest queued event</span>
          <span>{data.queue_age_seconds === null ? "Queue is empty" : `${data.queue_age_seconds} seconds`}</span>
        </div>
        <div className="ds-flex" style={{ margin: "16px 0", flexWrap: "wrap" }}>
          {can("autonomy.read") ? <button className="btn" onClick={() => readiness.mutate()} type="button">Check readiness</button> : null}
          {can("acquisition.read") ? <button className="btn" onClick={() => form.mutate()} type="button">Open the capture form</button> : null}
          <button className="btn" type="button" disabled={!selected} onClick={() => selected && preview.mutate(selected)}>Preview the next action</button>
          <Link className="btn" href="/admin/integrations">Connect the required integration</Link>
          {can("campaigns.write") ? (
            <>
              <label className="ds-flex" style={{ gap: 8, alignItems: "center" }}>
                <span>Offer</span>
                <select value={productId} onChange={(event) => setProductId(event.target.value)}>
                  <option value="">Choose a product</option>
                  {(data.marketing?.products ?? []).map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name} · {product.kind} · {product.list_price} {product.currency}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="btn"
                type="button"
                disabled={data.marketing?.status === "absent" && !productId}
                onClick={() => plan.mutate({ path: productId ? `start?product_id=${encodeURIComponent(productId)}&channel=linkedin` : "start" })}
              >
                Start operating plan
              </button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "research" })}>Research prospects</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "drafts" })}>Generate calendar draft</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "review", method: "GET" })}>Review pending versions</button>
              <button className="btn" type="button" disabled={!pending} onClick={() => pending && plan.mutate({ path: "authorize", body: { version_id: pending.id } })}>Authorize pending version</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "schedule", method: "GET" })}>Preview scheduled work</button>
              <button className="btn" type="button" disabled={!authorized} onClick={() => authorized && plan.mutate({ path: "schedule", body: { version_id: authorized.id } })}>Schedule authorized version</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "publish" })}>Publish the scheduled version</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "evidence", method: "GET" })}>Inspect publication evidence</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "outcomes", method: "GET" })}>Review attributed enquiries</button>
              <button className="btn" type="button" onClick={() => plan.mutate({ path: "resume" })}>Resolve blocker and resume</button>
            </>
          ) : null}
          {can("autonomy.write") && selected ? (
            <>
              <button className="btn" type="button" onClick={() => control.mutate({ id: selected, action: "continue" })}>Resume a corrected journey</button>
              <button className="btn" type="button" onClick={() => control.mutate({ id: selected, action: "pause" })}>Pause</button>
              <button className="btn" type="button" onClick={() => control.mutate({ id: selected, action: "resume" })}>Resume</button>
              <button className="btn" type="button" onClick={() => control.mutate({ id: selected, action: "cancel" })}>Cancel</button>
            </>
          ) : null}
        </div>
        {result ? <div className="callout"><div><strong>Action result</strong><p>{result}</p></div></div> : null}
        <h3>Discovery</h3>
        {data.discovery?.prospects?.length ? data.discovery.prospects.map((row) => (
          <div className="line-item" key={`${row.name}-${row.outcome}`}>
            <span>{row.name || "Unnamed prospect"} · {row.owner_name || "Unassigned"}</span>
            <span>{row.next_action}</span>
          </div>
        )) : <p className="muted">{data.discovery?.status === "failed" ? data.discovery.reason || "Discovery failed." : "No discovery result is stored."}</p>}
        <h3>Operating plan</h3>
        <div className="line-item">
          <span>{data.marketing?.offer_name ? `${data.marketing.offer_name} · ` : ""}{data.marketing?.status || "absent"} · {data.marketing?.next_action || "choose_product"}</span>
          <span>{data.marketing?.blocker || "No blocker is recorded."}</span>
        </div>
        <div className="line-item">
          <span>Attributed enquiries</span>
          <span>{data.marketing?.outcomes?.attributed_enquiries ?? 0}</span>
        </div>
        <div className="line-item">
          <span>Provider impressions</span>
          <span>{data.marketing?.outcomes?.impressions === null || data.marketing?.outcomes?.impressions === undefined ? "Unavailable" : data.marketing.outcomes.impressions}</span>
        </div>
        <div className="line-item">
          <span>Optimization</span>
          <span>{data.marketing?.outcomes?.optimization || "insufficient_evidence"}</span>
        </div>
        <h3>Journeys</h3>
        {data.journeys.length === 0 ? <p className="muted">No journey is active.</p> : data.journeys.map((row) => (
          <button className="row" key={row.journey_id} type="button" onClick={() => setJourneyId(row.journey_id)} style={{ width: "100%", textAlign: "left" }}>
            <div className="main">
              <h3>{row.lead_email || row.summary || row.workflow || "Journey"}</h3>
              <p>{row.status}{row.waiting_reason ? ` · ${row.waiting_reason}` : ""}{row.next_action ? ` · next ${row.next_action}` : ""}</p>
            </div>
            <span className="tag">{selected === row.journey_id ? "Selected" : row.business_state || row.status}</span>
          </button>
        ))}
        <h3>Running steps</h3>
        {data.running_steps.length === 0 ? <p className="muted">No step is running.</p> : data.running_steps.map((step) => (
          <div className="line-item" key={step.step_id}>
            <span>{step.name} · {step.lease_owner || "unleased"}</span>
            <span>{step.stale ? "Stale lease" : "Leased"}{step.age_seconds !== null ? ` · ${step.age_seconds}s` : ""}</span>
          </div>
        ))}
        <h3>Stale leases</h3>
        {data.stale_leases.length === 0 ? <p className="muted">No stale lease is recorded.</p> : data.stale_leases.map((step) => (
          <div className="line-item" key={`stale-${step.step_id}`}>
            <span>{step.name} · {step.lease_owner || "unleased"}</span>
            <span>Recover the worker before another send</span>
          </div>
        ))}
        <h3>Exceptions</h3>
        {data.exceptions.length === 0 ? <p className="muted">No journey is waiting on an exception.</p> : data.exceptions.map((row) => (
          <div className="line-item" key={`exception-${row.journey_id}`}>
            <span>{row.status}{row.waiting_reason ? ` · ${row.waiting_reason}` : ""}</span>
            <span>{row.next_action || "Review the journey"}</span>
          </div>
        ))}
        <h3>Recorded outcomes</h3>
        {outcomes.map(([name, value]) => (
          <div className="line-item" key={name}><span>{name.replaceAll("_", " ")}</span><span>{value}</span></div>
        ))}
        <h3>Evidence</h3>
        {data.evidence.length === 0 ? <p className="muted">No message, reply, or meeting evidence is stored.</p> : data.evidence.slice(0, 6).map((row, index) => (
          <div className="line-item" key={`${row.kind}-${row.provider_ref}-${index}`}>
            <span>{row.kind} · {row.status}</span>
            <span>{row.provider_ref || row.excerpt || "No provider reference"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
