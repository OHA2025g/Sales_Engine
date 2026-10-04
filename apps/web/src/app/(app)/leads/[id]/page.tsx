"use client";

import { Checks, Go, initials, Line, Notice, Panel } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { AutomationTrace } from "@/components/automation-trace";
import { Timeline } from "@/components/timeline";
import { Badge, Button, CheckField, Drawer, Field, FormActions, Input, Score, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { LEAD_STATUSES } from "@/lib/constants";
import { fullName, labelize } from "@/lib/format";
import type { Lead } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ["lead", params.id],
    queryFn: async () => (await api<Lead>(`/api/v1/leads/${params.id}`)).data,
    enabled: can("leads.read"),
  });
  const form = useForm<Lead>();

  const save = useMutation({
    mutationFn: (body: Lead) =>
      api(`/api/v1/leads/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          first_name: body.first_name,
          last_name: body.last_name,
          email: body.email,
          company_name: body.company_name,
          title: body.title,
          status: body.status,
          source: body.source,
          channel: body.channel,
          notes: body.notes,
          intent_score: body.intent_score,
          engagement_score: body.engagement_score,
          has_buying_trigger: body.has_buying_trigger,
          consent_email: body.consent_email,
          opt_out: body.opt_out,
          account_id: body.account_id,
        }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["lead", params.id] });
      setOpen(false);
    },
  });
  const score = useMutation({
    mutationFn: () => api(`/api/v1/leads/${params.id}/score`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["lead", params.id] }),
  });
  const nba = useMutation({
    mutationFn: () => api(`/api/v1/leads/${params.id}/nba`, { method: "POST" }),
  });
  const draft = useMutation({
    mutationFn: () =>
      api("/api/v1/ai/drafts/email", {
        method: "POST",
        body: JSON.stringify({ entity_type: "lead", entity_id: params.id, send: false }),
      }),
  });

  if (!can("leads.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the dossier" />;
  if (query.isError || !query.data) return <ErrorState message="This lead is not in your tenant." />;
  const lead = query.data;
  const parts = lead.latest_score;
  const nbaBody = nba.data?.data as { action?: string; reason?: string } | undefined;
  const draftBody = draft.data?.data as { subject?: string; body?: string } | undefined;

  return (
    <div>
      <PageHeader
        eyebrow="Lead dossier"
        title={fullName(lead.first_name, lead.last_name)}
        subtitle={`${lead.title || "Untitled"} · ${lead.company_name || "No company"}`}
        actions={
          <>
            {can("leads.write") ? (
              <Button
                variant="line"
                onClick={() => {
                  form.reset(lead);
                  setOpen(true);
                }}
              >
                Edit
              </Button>
            ) : null}
            {can("leads.score") ? (
              <Button variant="ghost" onClick={() => score.mutate()}>
                Recalculate score now
              </Button>
            ) : null}
            {can("ai.draft") ? <Button onClick={() => draft.mutate()}>Draft email</Button> : null}
          </>
        }
      />
      <Notice
        title="Next expected outcome: qualified discovery"
        body="Confirm the buyer’s success criteria, technical stakeholder, and decision process before opportunity handoff."
      />
      <div className="ds-grid wide">
        <Panel title="Lead context">
          <div className="ds-flex">
            <span className="avatar square">{initials(fullName(lead.first_name, lead.last_name))}</span>
            <div>
              <h2>{fullName(lead.first_name, lead.last_name)}</h2>
              <div className="small muted">{lead.title || "Title not recorded"} · {lead.company_name || "No company"}</div>
            </div>
            <span className="ds-grow" />
            <Badge tone={lead.status === "qualified" ? "ok" : "blue"}>{labelize(lead.status)}</Badge>
          </div>
          <hr className="rule" />
          <Line label="Fit assessment" value={parts?.total != null ? `${parts.total} / 100 · evidence attached` : "Not scored"} />
          <Line label="Source" value={lead.source || "Not recorded"} />
          <Line label="Channel" value={lead.channel || "Not recorded"} />
          <Line label="Contact eligibility" value={lead.opt_out ? "Opted out" : lead.consent_email ? "Email permitted · current" : "Consent not recorded"} />
          <Line label="Buying trigger" value={lead.has_buying_trigger ? "Recorded" : "Not recorded"} />
          <div className="ds-flex" style={{ marginTop: 18 }}>
            {lead.account_id ? <Go href={`/accounts/${lead.account_id}`}>Account</Go> : null}
            <Go href="/contacts">Contact</Go>
            <Go href="/meetings">Meeting</Go>
            <Go href="/automation/runs">Execution</Go>
          </div>
        </Panel>
        <Panel title="Qualification evidence">
          <Checks
            items={[
              { label: "Business need identified", ok: Boolean(lead.notes || lead.has_buying_trigger) },
              { label: "Sponsor relationship confirmed", ok: lead.status === "qualified" || lead.status === "converted" },
              { label: "Permitted contact scope present", ok: lead.consent_email && !lead.opt_out },
              { label: "Technical evaluator mapped", ok: Boolean(lead.title) },
              { label: "Success criteria and timing confirmed", ok: lead.status === "qualified" },
            ]}
          />
          <hr className="rule" />
          <span className="small muted">The meeting outcome controls the opportunity handoff.</span>
          <div style={{ marginTop: 16 }}>
            <Go href="/meetings" primary>Record meeting outcome</Go>
          </div>
          <Button variant="line" onClick={() => nba.mutate()}>Next best action</Button>
          {nbaBody?.action ? <p>{nbaBody.action}</p> : null}
          {nbaBody?.reason ? <p className="small muted">{nbaBody.reason}</p> : null}
        </Panel>
      </div>
      <div className="grid gap-4 xl:grid-cols-3 section-gap">
        <div className="panel p-5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--muted)]">Score</p>
          <div className="mt-3 flex items-end gap-3">
            <p className="text-5xl font-semibold text-navy">{parts?.total ?? "—"}</p>
            <Score value={parts?.total} />
          </div>
          <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{parts?.reasons || "Score the lead to persist a breakdown."}</p>
          {parts ? (
            <ul className="mt-5 space-y-2 text-sm">
              {[
                ["ICP fit", parts.icp_fit],
                ["Intent", parts.intent],
                ["Engagement", parts.engagement],
                ["Persona", parts.persona],
                ["Company", parts.company_potential],
                ["Trigger", parts.buying_trigger],
                ["Timing", parts.timing],
              ].map(([label, value]) => (
                <li key={String(label)} className="flex justify-between">
                  <span className="text-[var(--muted)]">{label}</span>
                  {value}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className="panel p-5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--muted)]">Record</p>
          <ul className="mt-4 space-y-3 text-sm">
            <li className="flex justify-between"><span className="text-[var(--muted)]">Status</span><Badge>{labelize(lead.status)}</Badge></li>
            <li className="flex justify-between"><span className="text-[var(--muted)]">Source</span>{lead.source || "—"}</li>
            <li className="flex justify-between"><span className="text-[var(--muted)]">Channel</span>{lead.channel || "—"}</li>
            <li className="flex justify-between"><span className="text-[var(--muted)]">Consent</span>{lead.opt_out ? "opted out" : lead.consent_email ? "email ok" : "none"}</li>
          </ul>
          <Button variant="line" className="mt-6" onClick={() => nba.mutate()}>
            Next best action
          </Button>
          {nbaBody?.action ? (
            <p className="mt-3 text-sm leading-6 text-ink">
              {nbaBody.action}
              <span className="mt-1 block text-[var(--muted)]">{nbaBody.reason}</span>
            </p>
          ) : null}
        </div>
        <div className="panel p-5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--muted)]">Draft</p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--muted)]">
            {draftBody?.subject ? `${draftBody.subject}\n\n` : ""}
            {draftBody?.body ?? "Drafts are stored. Send waits in Approvals until a live provider exists."}
          </p>
        </div>
      </div>
      <div className="mt-8 grid gap-4 xl:grid-cols-2">
        <AutomationTrace entityType="lead" entityId={lead.id} />
        <div>
          <h2 className="mb-4 text-xl font-semibold text-navy">Ledger</h2>
          <Timeline entityType="lead" entityId={lead.id} />
        </div>
      </div>
      <Drawer open={open} title="Edit lead" onClose={() => setOpen(false)}>
        <form onSubmit={form.handleSubmit((values) => save.mutate(values))} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="First name"><Input {...form.register("first_name", { required: true })} /></Field>
            <Field label="Last name"><Input {...form.register("last_name", { required: true })} /></Field>
          </div>
          <Field label="Email"><Input {...form.register("email")} /></Field>
          <Field label="Company"><Input {...form.register("company_name")} /></Field>
          <Field label="Title"><Input {...form.register("title")} /></Field>
          <Field label="Status">
            <Select {...form.register("status")}>
              {LEAD_STATUSES.map((item) => (
                <option key={item} value={item}>{labelize(item)}</option>
              ))}
            </Select>
          </Field>
          <Field label="Notes"><Textarea rows={4} {...form.register("notes")} /></Field>
          <CheckField label="Buying trigger" {...form.register("has_buying_trigger")} />
          <CheckField label="Email consent" {...form.register("consent_email")} />
          <FormActions pending={save.isPending} onCancel={() => setOpen(false)} />
        </form>
      </Drawer>
    </div>
  );
}
