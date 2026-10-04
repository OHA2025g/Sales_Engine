"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Button, Field, Input, Select } from "@/components/ui";
import { ConfirmDialog, SectionCard, StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import type { AutopilotSettings } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

export default function PoliciesPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [name, setName] = useState("Inbound email");
  const [mode, setMode] = useState("assisted");
  const [notice, setNotice] = useState("");
  const settings = useQuery({
    queryKey: ["autopilot-settings"],
    queryFn: async () => (await api<AutopilotSettings>("/api/v1/autonomy/settings")).data,
    enabled: can("autonomy.read"),
  });
  const pause = useMutation({
    mutationFn: () => api("/api/v1/autonomy/settings", { method: "PATCH", body: JSON.stringify({ emergency_stop: true }) }),
    onSuccess: () => {
      setConfirm(false);
      void client.invalidateQueries({ queryKey: ["autopilot-settings"] });
    },
  });
  const grant = useMutation({
    mutationFn: () =>
      api("/api/v1/workflow/grants", {
        method: "POST",
        body: JSON.stringify({ name, mode, workflow: "inbound", channel: "email", volume_cap: 25, cost_cap: 0 }),
      }),
    onSuccess: () => setNotice("Grant saved. It covers the named workflow and channel only."),
    onError: (error: Error) => setNotice(error.message),
  });
  if (!can("autonomy.read")) return <DeniedState />;
  if (settings.isLoading) return <LoadingState label="Loading policies" />;
  if (settings.isError || !settings.data) return <ErrorState message="Policies could not be loaded." />;
  const current = settings.data;
  return (
    <div>
      <PageHeader
        eyebrow="Autopilot"
        title="Policies"
        subtitle="A scoped grant is required before a send can run with approval turned off. Pause stops every channel."
        nextHref="/forecast"
        nextLabel="Forecast"
        actions={
          can("autonomy.write") ? (
            <Button variant="line" onClick={() => setConfirm(true)} disabled={current.emergency_stop}>
              Pause journeys
            </Button>
          ) : null
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <StatusPill tone={current.emergency_stop ? "blocked" : "success"}>{current.emergency_stop ? "Stopped" : "Running"}</StatusPill>
        <StatusPill tone="info">Minimum score {current.minimum_lead_score}</StatusPill>
        <StatusPill tone="neutral">Quiet hours {current.quiet_hours_start}–{current.quiet_hours_end}</StatusPill>
      </div>
      <SectionCard title="Scoped grant">
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            grant.mutate();
          }}
        >
          <Field label="Name"><Input value={name} onChange={(event) => setName(event.target.value)} /></Field>
          <Field label="Mode">
            <Select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="observe">Observe</option>
              <option value="assisted">Assisted</option>
              <option value="bounded_autopilot">Bounded autopilot</option>
            </Select>
          </Field>
          <div className="md:col-span-2">
            <Button type="submit" disabled={grant.isPending}>Save grant</Button>
            {notice ? <p className="mt-2 text-sm text-[var(--muted)]">{notice}</p> : null}
          </div>
        </form>
      </SectionCard>
      <ConfirmDialog
        open={confirm}
        title="Pause every journey?"
        body="This sets the emergency stop. Social, ads, and sends stay blocked until the stop is cleared."
        confirmLabel="Pause"
        pending={pause.isPending}
        onCancel={() => setConfirm(false)}
        onConfirm={() => pause.mutate()}
      />
    </div>
  );
}
