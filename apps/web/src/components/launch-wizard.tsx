"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

type Profile = {
  company_name: string;
  summary: string;
  audience: string;
  website: string;
  proof: string;
  capture_url: string;
};

type Launch = { can_run_inbound: boolean; autonomy_mode: string; steps: { key: string; ready: boolean; detail: string }[] };

const STEPS = ["Company and offer", "Objective and audience", "Channels and ownership", "Policies and limits", "Dry run and launch"];

export function LaunchWizard() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [step, setStep] = useState(0);
  const [notice, setNotice] = useState("");
  const [company, setCompany] = useState("");
  const [summary, setSummary] = useState("");
  const [audience, setAudience] = useState("");
  const [website, setWebsite] = useState("");
  const [objective, setObjective] = useState("");
  const [target, setTarget] = useState("0");
  const [channel, setChannel] = useState("email");
  const [budget, setBudget] = useState("0");
  const [mode, setMode] = useState("assisted");
  const profile = useQuery({
    queryKey: ["content-profile"],
    queryFn: async () => (await api<Profile>("/api/v1/content/profile")).data,
    enabled: can("campaigns.read"),
  });
  const launch = useQuery({
    queryKey: ["workflow-launch"],
    queryFn: async () => (await api<Launch>("/api/v1/workflow/launch")).data,
    enabled: can("autonomy.read"),
  });
  const saveCompany = useMutation({
    mutationFn: () =>
      api("/api/v1/content/profile", {
        method: "PUT",
        body: JSON.stringify({
          company_name: company || profile.data?.company_name || "",
          summary: summary || profile.data?.summary || "",
          audience: audience || profile.data?.audience || "",
          website: website || profile.data?.website || "",
          proof: profile.data?.proof || "",
          capture_url: profile.data?.capture_url || "",
        }),
      }),
    onSuccess: () => {
      setNotice("Company and offer saved.");
      setStep(1);
      void client.invalidateQueries({ queryKey: ["content-profile"] });
    },
    onError: (error: Error) => setNotice(error.message),
  });
  const saveObjective = useMutation({
    mutationFn: () =>
      api("/api/v1/workflow/objectives", {
        method: "POST",
        body: JSON.stringify({ name: objective, segment: audience, target_measure: "qualified_pipeline", target_amount: Number(target) }),
      }),
    onSuccess: () => {
      setNotice("Objective saved.");
      setStep(2);
    },
    onError: (error: Error) => setNotice(error.message),
  });
  const savePlan = useMutation({
    mutationFn: () =>
      api("/api/v1/workflow/campaign-plans", {
        method: "POST",
        body: JSON.stringify({ name: objective || "Launch plan", channel, budget: Number(budget), audience, status: "approved" }),
      }),
    onSuccess: () => {
      setNotice("Channel plan saved. Product price was not used as the budget.");
      setStep(3);
    },
    onError: (error: Error) => setNotice(error.message),
  });
  const saveGrant = useMutation({
    mutationFn: () =>
      api("/api/v1/workflow/grants", {
        method: "POST",
        body: JSON.stringify({ name: "Launch grant", mode, workflow: "inbound", channel, volume_cap: 25, cost_cap: Number(budget) }),
      }),
    onSuccess: () => {
      setNotice("Policy saved.");
      setStep(4);
      void client.invalidateQueries({ queryKey: ["workflow-launch"] });
    },
    onError: (error: Error) => setNotice(error.message),
  });

  if (!can("autonomy.read")) return <DeniedState />;
  if (launch.isLoading || profile.isLoading) return <LoadingState label="Loading launch" />;
  if (launch.isError) return <ErrorState message="Launch readiness could not be loaded." />;

  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="Revenue launch"
        subtitle="Five steps. A connected channel is not a campaign, and a dry run does not send."
        nextHref="/knowledge"
        nextLabel="Knowledge"
      />
      <ol className="mb-6 grid gap-2 md:grid-cols-5">
        {STEPS.map((label, index) => (
          <li key={label}>
            <button
              type="button"
              className="w-full rounded-md border border-[var(--line)] px-3 py-2 text-left text-xs"
              onClick={() => setStep(index)}
            >
              <span className="block text-[var(--meta)]">0{index + 1}</span>
              <span className={index === step ? "text-ink" : "text-[var(--muted)]"}>{label}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="panel max-w-3xl space-y-4 p-5">
        {step === 0 ? (
          <>
            <Field label="Company"><Input value={company} placeholder={profile.data?.company_name} onChange={(event) => setCompany(event.target.value)} /></Field>
            <Field label="Offer"><Textarea rows={4} value={summary} placeholder={profile.data?.summary} onChange={(event) => setSummary(event.target.value)} /></Field>
            <Field label="Website"><Input value={website} placeholder={profile.data?.website} onChange={(event) => setWebsite(event.target.value)} /></Field>
            {can("campaigns.write") ? <Button onClick={() => saveCompany.mutate()} disabled={saveCompany.isPending}>Save company</Button> : null}
          </>
        ) : null}
        {step === 1 ? (
          <>
            <Field label="Audience"><Input value={audience} placeholder={profile.data?.audience} onChange={(event) => setAudience(event.target.value)} /></Field>
            <Field label="Objective"><Input value={objective} onChange={(event) => setObjective(event.target.value)} required /></Field>
            <Field label="Qualified pipeline target"><Input value={target} onChange={(event) => setTarget(event.target.value)} /></Field>
            {can("campaigns.write") ? <Button onClick={() => saveObjective.mutate()} disabled={saveObjective.isPending}>Save objective</Button> : null}
          </>
        ) : null}
        {step === 2 ? (
          <>
            <Field label="Channel">
              <Select value={channel} onChange={(event) => setChannel(event.target.value)}>
                <option value="email">Email</option>
                <option value="linkedin">LinkedIn</option>
                <option value="inbound">Inbound</option>
              </Select>
            </Field>
            <Field label="Approved budget"><Input value={budget} onChange={(event) => setBudget(event.target.value)} /></Field>
            {can("campaigns.write") ? <Button onClick={() => savePlan.mutate()} disabled={savePlan.isPending}>Save channel plan</Button> : null}
          </>
        ) : null}
        {step === 3 ? (
          <>
            <Field label="Grant mode">
              <Select value={mode} onChange={(event) => setMode(event.target.value)}>
                <option value="observe">Observe</option>
                <option value="assisted">Assisted</option>
                <option value="bounded_autopilot">Bounded autopilot</option>
              </Select>
            </Field>
            <Button onClick={() => saveGrant.mutate()} disabled={saveGrant.isPending}>Save policy</Button>
          </>
        ) : null}
        {step === 4 ? (
          <div className="space-y-3">
            <StatusPill tone={launch.data?.can_run_inbound ? "success" : "review"}>
              {launch.data?.can_run_inbound ? "Inbound can run" : "Inbound is not ready"}
            </StatusPill>
            <p className="text-sm text-[var(--muted)]">Autonomy mode: {launch.data?.autonomy_mode}</p>
            <ul className="space-y-2">
              {(launch.data?.steps ?? []).map((item) => (
                <li key={item.key} className="flex items-start justify-between gap-3 text-sm">
                  <span>{item.detail}</span>
                  <StatusPill tone={item.ready ? "success" : "blocked"}>{item.ready ? "Ready" : "Blocked"}</StatusPill>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {notice ? <p className="text-sm text-[var(--muted)]">{notice}</p> : null}
      </div>
    </div>
  );
}
