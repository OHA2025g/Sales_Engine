"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { ICP, Market } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

export default function StrategyPage() {
  const { can } = useAuth();
  const [name, setName] = useState("");
  const [segment, setSegment] = useState("");
  const [amount, setAmount] = useState("0");
  const [notice, setNotice] = useState("");
  const icps = useQuery({
    queryKey: ["icps"],
    queryFn: async () => (await api<ICP[]>("/api/v1/icps")).data ?? [],
    enabled: can("icps.read"),
  });
  const markets = useQuery({
    queryKey: ["markets"],
    queryFn: async () => (await api<Market[]>("/api/v1/markets")).data ?? [],
    enabled: can("markets.read"),
  });
  const save = useMutation({
    mutationFn: () =>
      api("/api/v1/workflow/objectives", {
        method: "POST",
        body: JSON.stringify({ name, segment, target_measure: "qualified_pipeline", target_amount: Number(amount), period: "" }),
      }),
    onSuccess: () => setNotice("Objective saved for this tenant."),
    onError: (error: Error) => setNotice(error.message),
  });
  if (!can("icps.read")) return <DeniedState />;
  if (icps.isLoading) return <LoadingState label="Loading strategy" />;
  if (icps.isError) return <ErrorState message="ICPs could not be loaded." />;
  return (
    <div>
      <PageHeader
        eyebrow="Strategy & Intelligence"
        title="Revenue strategy"
        subtitle="Who we sell to, which markets are scored, and the objective the launch will use."
        nextHref="/icps"
        nextLabel="Ideal customer profiles"
      />
      <div className="ds-grid wide">
        <section className="panel">
          <header className="panel-head">
            <h2>Ideal customer profiles</h2>
            <Link className="btn" href="/icps">Review ICPs</Link>
          </header>
          <div className="panel-body">
            {(icps.data ?? []).length === 0 ? (
              <EmptyState title="No ICP" body="Add the audience before a campaign can target it." />
            ) : (
              (icps.data ?? []).map((row) => (
                <div className="line-item" key={row.id}>
                  <span>{row.name}</span>
                  <span>{row.industries || "Industries not set"} · {row.geographies || "Geography not set"}</span>
                </div>
              ))
            )}
          </div>
        </section>
        <section className="panel">
          <header className="panel-head">
            <h2>Markets</h2>
            <Link className="btn" href="/market">Review markets</Link>
          </header>
          <div className="panel-body">
            {markets.isError ? (
              <p>Markets could not be loaded.</p>
            ) : (markets.data ?? []).length === 0 ? (
              <EmptyState title="No markets" body="Score a market before treating it as a source of accounts." />
            ) : (
              (markets.data ?? []).slice(0, 6).map((row) => (
                <div className="line-item" key={row.id}>
                  <span>{row.name}</span>
                  <span className="num">{row.attractiveness}</span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
      {can("campaigns.write") ? (
        <form
          className="panel mt-4 grid gap-3 p-5 md:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <Field label="Objective">
            <Input value={name} onChange={(event) => setName(event.target.value)} required />
          </Field>
          <Field label="Audience">
            <Input value={segment} onChange={(event) => setSegment(event.target.value)} />
          </Field>
          <Field label="Qualified pipeline target">
            <Input value={amount} onChange={(event) => setAmount(event.target.value)} />
          </Field>
          <div className="md:col-span-3">
            <Button type="submit" disabled={save.isPending}>Save objective</Button>
            {notice ? <p className="mt-2 text-sm text-[var(--muted)]">{notice}</p> : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}
