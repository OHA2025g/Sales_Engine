"use client";

import { DataTable } from "@/components/data-table";
import { Go, Panel, Stats } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Drawer, Field, FormActions, Input, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { money } from "@/lib/format";
import type { Opportunity, Product, Quote } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";

type QuoteForm = { opportunity_id: string; product_id: string; quantity: number; discount_pct: number; tax_pct: number };

export default function CommercialPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const form = useForm<QuoteForm>({ defaultValues: { opportunity_id: "", product_id: "", quantity: 1, discount_pct: 0, tax_pct: 0 } });
  const products = useQuery({
    queryKey: ["products"],
    queryFn: async () => (await api<Product[]>("/api/v1/lifecycle/products")).data ?? [],
    enabled: can("commercial.read"),
  });
  const quotes = useQuery({
    queryKey: ["quotes"],
    queryFn: async () => (await api<Quote[]>("/api/v1/lifecycle/quotes")).data ?? [],
    enabled: can("commercial.read"),
  });
  const opps = useQuery({
    queryKey: ["opportunities"],
    queryFn: async () => (await api<Opportunity[]>("/api/v1/opportunities")).data ?? [],
    enabled: can("opportunities.read") && open,
  });
  const accept = useMutation({
    mutationFn: (quoteId: string) => api(`/api/v1/workflow/quotes/${quoteId}/accept`, { method: "POST", body: JSON.stringify({ note: "" }) }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["quotes"] }),
  });
  const create = useMutation({
    mutationFn: (body: QuoteForm) =>
      api("/api/v1/lifecycle/quotes", {
        method: "POST",
        body: JSON.stringify({
          opportunity_id: body.opportunity_id,
          discount_pct: Number(body.discount_pct),
          tax_pct: Number(body.tax_pct),
          lines: [{ product_id: body.product_id, quantity: Number(body.quantity) }],
        }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["quotes"] });
      void client.invalidateQueries({ queryKey: ["approvals"] });
      setOpen(false);
    },
  });

  if (!can("commercial.read")) return <DeniedState />;
  if (products.isLoading || quotes.isLoading) return <LoadingState label="Reading the catalog" />;
  if (products.isError || quotes.isError) return <ErrorState message="Commercial could not be assembled." />;

  return (
    <div>
      <PageHeader
        eyebrow="Commercial"
        title="Quotes"
        subtitle="Discount of 10% or more needs approval of that quote version. Editing the quote after approval makes the old authorization stale. Accepted business is not forecast."
        actions={can("commercial.write") ? <Button onClick={() => setOpen(true)}>New quote</Button> : null}
      />
      <Stats
        items={[
          { name: "Quotes under review", value: String((quotes.data ?? []).filter((row) => row.approval_required).length), note: "Version-bound decisions" },
          { name: "Authorized quotes", value: String((quotes.data ?? []).filter((row) => row.status === "approved").length), note: "Ready for permitted delivery" },
          { name: "Acceptance pending", value: String((quotes.data ?? []).filter((row) => row.status === "sent" || row.status === "approved").length), note: "Buyer action needed" },
          { name: "Active products", value: String((products.data ?? []).length), note: "Approved catalog" },
        ]}
      />
      <div className="ds-grid wide">
        <Panel title="Quotes" extra={<Go href="/commercial/proposal">Proposal workspace</Go>} body={false}>
          {(quotes.data ?? []).length === 0 ? (
            <div className="empty"><h3>No quotes</h3><p>A quote is a versioned commercial record, not a forecast.</p></div>
          ) : (
            <DataTable
              bare
              rows={quotes.data ?? []}
              columns={[
                {
                  key: "id",
                  header: "Quote / customer",
                  cell: (row) => (
                    <Link className="record-link" href={`/commercial/quotes/${row.id}`}>
                      <span>{row.id.slice(0, 8)}</span>
                    </Link>
                  ),
                },
                { key: "total", header: "Value", cell: (row) => <span className="num">{money(row.total)}</span> },
                { key: "status", header: "Authorization", cell: (row) => <Badge tone={row.status === "accepted" || row.status === "approved" ? "ok" : "gold"}>{row.status}</Badge> },
                {
                  key: "next",
                  header: "Next step",
                  cell: (row) =>
                    can("commercial.write") && row.status === "approved" ? (
                      <Button variant="line" onClick={() => accept.mutate(row.id)}>Accept</Button>
                    ) : row.status === "accepted" ? "Recorded" : row.approval_required ? "Authorize discount" : "Review version",
                },
              ]}
            />
          )}
        </Panel>
        <Panel title="Approved catalog" body={false}>
          {(products.data ?? []).length === 0 ? (
            <div className="empty"><h3>No products</h3><p>Add SKUs before quoting.</p></div>
          ) : (
            (products.data ?? []).map((row) => (
              <div className="row" key={row.id}>
                <div className="main">
                  <h3>{row.name}</h3>
                  <p>{row.sku}</p>
                </div>
                <span className="num">{money(row.list_price)}</span>
              </div>
            ))
          )}
        </Panel>
      </div>
      <Drawer open={open} title="New quote" onClose={() => setOpen(false)}>
        <form onSubmit={form.handleSubmit((values) => create.mutate(values))} className="space-y-4">
          <Field label="Opportunity">
            <Select {...form.register("opportunity_id", { required: true })}>
              <option value="">Select</option>
              {(opps.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </Select>
          </Field>
          <Field label="Product">
            <Select {...form.register("product_id", { required: true })}>
              <option value="">Select</option>
              {(products.data ?? []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </Select>
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Qty"><Input type="number" {...form.register("quantity", { valueAsNumber: true })} /></Field>
            <Field label="Discount %"><Input type="number" {...form.register("discount_pct", { valueAsNumber: true })} /></Field>
            <Field label="Tax %"><Input type="number" {...form.register("tax_pct", { valueAsNumber: true })} /></Field>
          </div>
          <FormActions pending={create.isPending} onCancel={() => setOpen(false)} />
        </form>
      </Drawer>
    </div>
  );
}
