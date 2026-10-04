"use client";

import { ListToolbar } from "@/components/list-toolbar";
import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Drawer, Field, FormActions, Input, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { OPP_STAGES } from "@/lib/constants";
import { labelize, money } from "@/lib/format";
import { qs, useDebounced } from "@/lib/hooks";
import type { Account, Opportunity } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";

type OppForm = {
  account_id: string;
  name: string;
  stage: string;
  amount: string;
  next_step: string;
  expected_close: string;
};

export default function PipelinePage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("");
  const [open, setOpen] = useState(false);
  const search = useDebounced(q);
  const form = useForm<OppForm>({
    defaultValues: { account_id: "", name: "", stage: "qualification", amount: "0", next_step: "", expected_close: "" },
  });

  const query = useQuery({
    queryKey: ["opportunities", search, stage],
    queryFn: async () =>
      (await api<Opportunity[]>(`/api/v1/opportunities${qs({ q: search, stage, page_size: 100 })}`)).data ?? [],
    enabled: can("opportunities.read"),
  });
  const accounts = useQuery({
    queryKey: ["accounts-options"],
    queryFn: async () => (await api<Account[]>("/api/v1/accounts?page_size=100")).data ?? [],
    enabled: open && can("accounts.read"),
  });
  const create = useMutation({
    mutationFn: (body: OppForm) =>
      api("/api/v1/opportunities", {
        method: "POST",
        body: JSON.stringify({
          ...body,
          amount: Number(body.amount || 0),
          expected_close: body.expected_close || null,
        }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["opportunities"] });
      setOpen(false);
      form.reset();
    },
  });

  if (!can("opportunities.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Laying the board" />;
  if (query.isError) return <ErrorState message="Pipeline could not be assembled." />;
  const rows = query.data ?? [];
  const stages = Array.from(new Set([...OPP_STAGES, ...rows.map((row) => row.stage)]));
  const visible = stage ? [stage] : stages;

  return (
    <div>
      <PageHeader
        eyebrow="Sales"
        title="Opportunity pipeline"
        subtitle="Qualified opportunities, stage totals, and the next owned step."
        nextHref="/commercial"
        nextLabel="Quotes & catalog"
      />
      <ListToolbar
        query={q}
        onQuery={setQ}
        filter={stage}
        onFilter={setStage}
        filterOptions={[{ value: "", label: "All stages" }, ...stages.map((item) => ({ value: item, label: labelize(item) }))]}
        onCreate={can("opportunities.write") ? () => setOpen(true) : undefined}
        createLabel="Open an opportunity"
      />
      {rows.length === 0 ? (
        <EmptyState title="The board is empty" body="Open an opportunity from a live account. No decorative deals are invented." />
      ) : (
        <div className="board">
          {visible.map((column) => {
            const cards = rows.filter((row) => row.stage === column);
            const sum = cards.reduce((acc, row) => acc + Number(row.amount || 0), 0);
            return (
              <section key={column} className="board-col">
                <div className="board-head">
                  <strong>{labelize(column)}</strong>
                  <span className="muted num">{money(sum)}</span>
                </div>
                {cards.length === 0 ? <p className="small muted">No deals.</p> : null}
                {cards.map((row) => {
                  const attention = !row.next_step;
                  return (
                    <Link key={row.id} href={`/opportunities/${row.id}`} className="deal-card">
                      <div className="upper">{row.probability}% probability</div>
                      <h3>{row.name}</h3>
                      <span className="amount num">{money(row.amount)}</span>
                      <p className="small muted">{row.next_step || "Next step not recorded"}</p>
                      <div className="between">
                        <Badge tone={attention ? "gold" : "ok"}>{attention ? "Needs attention" : "Progressing"}</Badge>
                        <span className="small muted">{row.expected_close || "Date unavailable"}</span>
                      </div>
                    </Link>
                  );
                })}
              </section>
            );
          })}
        </div>
      )}
      <Drawer open={open} title="Open an opportunity" onClose={() => setOpen(false)}>
        <form onSubmit={form.handleSubmit((values) => create.mutate(values))} className="space-y-4">
          <Field label="Account">
            <Select {...form.register("account_id", { required: true })}>
              <option value="">Select account</option>
              {(accounts.data ?? []).map((row) => (
                <option key={row.id} value={row.id}>{row.name}</option>
              ))}
            </Select>
          </Field>
          <Field label="Name"><Input {...form.register("name", { required: true })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Stage">
              <Select {...form.register("stage")}>
                {OPP_STAGES.map((item) => <option key={item} value={item}>{labelize(item)}</option>)}
              </Select>
            </Field>
            <Field label="Amount"><Input type="number" {...form.register("amount")} /></Field>
          </div>
          <Field label="Expected close"><Input type="date" {...form.register("expected_close")} /></Field>
          <Field label="Next step"><Textarea rows={3} {...form.register("next_step")} /></Field>
          <FormActions pending={create.isPending} onCancel={() => setOpen(false)} label="Create opportunity" />
        </form>
      </Drawer>
    </div>
  );
}
