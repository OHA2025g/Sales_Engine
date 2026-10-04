"use client";

import { DataTable } from "@/components/data-table";
import { Go, Notice } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Drawer, Field, FormActions, Input, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { labelize } from "@/lib/format";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

type Profile = {
  id: string | null;
  company_name: string;
  summary: string;
  audience: string;
  website: string;
  proof: string;
  capture_url: string;
};

type Product = {
  id: string;
  sku: string;
  name: string;
  description: string;
  kind: string;
  list_price: string;
  currency: string;
};

type Draft = {
  id: string;
  channel: string;
  kind: string;
  headline: string;
  body: string;
  cta: string;
  brief: string;
  destination_url: string;
  image_url: string;
  status: string;
  error: string;
};

type ProfileForm = Omit<Profile, "id">;
type ProductForm = { sku: string; name: string; description: string };
type GenerateForm = { product_id: string; ad_channel: string; brief: string };
type DraftForm = { headline: string; body: string; cta: string; image_url: string };

function tone(status: string): "ok" | "rose" | "gold" {
  if (status === "published" || status === "paused") return "ok";
  if (status === "failed") return "rose";
  return "gold";
}

export default function ContentPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [editing, setEditing] = useState<Draft | null>(null);
  const profileForm = useForm<ProfileForm>({
    defaultValues: { company_name: "", summary: "", audience: "", website: "", proof: "", capture_url: "" },
  });
  const productForm = useForm<ProductForm>({ defaultValues: { sku: "", name: "", description: "" } });
  const generateForm = useForm<GenerateForm>({ defaultValues: { product_id: "", ad_channel: "linkedin", brief: "" } });
  const draftForm = useForm<DraftForm>({ defaultValues: { headline: "", body: "", cta: "", image_url: "" } });

  const profile = useQuery({
    queryKey: ["content-profile"],
    queryFn: async () => (await api<Profile>("/api/v1/content/profile")).data,
    enabled: can("campaigns.read"),
  });
  const products = useQuery({
    queryKey: ["content-products"],
    queryFn: async () => (await api<Product[]>("/api/v1/content/products")).data ?? [],
    enabled: can("campaigns.read"),
  });
  const drafts = useQuery({
    queryKey: ["content-drafts"],
    queryFn: async () => (await api<Draft[]>("/api/v1/content/drafts")).data ?? [],
    enabled: can("campaigns.read"),
  });

  const saveProfile = useMutation({
    mutationFn: (body: ProfileForm) => api("/api/v1/content/profile", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["content-profile"] }),
  });
  const addProduct = useMutation({
    mutationFn: (body: ProductForm) => api("/api/v1/content/products", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["content-products"] });
      productForm.reset();
    },
  });
  const generate = useMutation({
    mutationFn: (body: GenerateForm) => api("/api/v1/content/generate", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      generateForm.setValue("brief", "");
      void client.invalidateQueries({ queryKey: ["content-drafts"] });
    },
  });
  const saveDraft = useMutation({
    mutationFn: (body: DraftForm & { id: string }) =>
      api(`/api/v1/content/drafts/${body.id}`, {
        method: "PATCH",
        body: JSON.stringify({ headline: body.headline, body: body.body, cta: body.cta, image_url: body.image_url }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["content-drafts"] });
      setEditing(null);
    },
  });
  const publish = useMutation({
    mutationFn: (id: string) => api(`/api/v1/content/drafts/${id}/publish`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["content-drafts"] }),
  });
  const saved = profile.data;
  useEffect(() => {
    if (!saved) return;
    profileForm.reset({
      company_name: saved.company_name,
      summary: saved.summary,
      audience: saved.audience,
      website: saved.website,
      proof: saved.proof,
      capture_url: saved.capture_url,
    });
  }, [saved, profileForm]);

  if (!can("campaigns.read")) return <DeniedState />;
  if (profile.isLoading || products.isLoading || drafts.isLoading) return <LoadingState label="Reading content drafts" />;
  if (profile.isError || products.isError || drafts.isError) return <ErrorState message="Content could not be loaded." />;

  const catalog = products.data ?? [];
  const rows = drafts.data ?? [];

  return (
    <div>
      <PageHeader
        eyebrow="Create"
        title="Content"
        subtitle="Gemini writes the full post and ad from your company and product. A short note is optional. It reads what was already sent so the next draft is different. Nothing goes out until you publish it."
      />
      <Notice
        title="Grounded content, connected to a campaign"
        body="Every asset retains its brief, approved claims, version, reviewer, and distribution result."
      />
      <div className="ds-grid three">
        {rows.length === 0 ? (
          <div className="panel empty">
            <h3>No assets yet</h3>
            <p>Generate a draft from the company profile. Nothing is published until you send it.</p>
          </div>
        ) : (
          rows.map((row) => (
            <section className="panel workspace-card" key={row.id}>
              <div className="between">
                <span className="upper">{labelize(row.channel || row.kind)}</span>
                <Badge tone={tone(row.status)}>{labelize(row.status)}</Badge>
              </div>
              <h2>{row.headline || "Untitled asset"}</h2>
              <p>{row.brief || row.cta || "No brief recorded"}</p>
              <div className="ds-flex">
                <Go href={`/content/${row.id}`}>Open editor</Go>
                <Go href="/campaigns">View campaign</Go>
              </div>
            </section>
          ))
        )}
      </div>
      <form
        className="panel mb-6 grid gap-4 p-4 md:grid-cols-2"
        onSubmit={profileForm.handleSubmit((values) => saveProfile.mutate(values))}
      >
        <Field label="Company name">
          <Input {...profileForm.register("company_name", { required: true })} />
        </Field>
        <Field label="Who you sell to">
          <Input {...profileForm.register("audience")} />
        </Field>
        <Field label="What you do">
          <Textarea rows={4} {...profileForm.register("summary", { required: true })} />
        </Field>
        <Field label="Proof you are willing to claim">
          <Textarea rows={4} {...profileForm.register("proof")} />
        </Field>
        <Field label="Website">
          <Input {...profileForm.register("website")} placeholder="https://" />
        </Field>
        <Field label="Lead capture link">
          <Input {...profileForm.register("capture_url")} placeholder="https://your-host/capture/…" />
        </Field>
        <div className="md:col-span-2 flex items-center gap-3">
          <Button type="submit" disabled={saveProfile.isPending || !can("campaigns.write")}>
            {saveProfile.isPending ? "Saving…" : "Save company"}
          </Button>
          {saveProfile.isSuccess ? <p className="text-sm text-emerald-700">Company saved.</p> : null}
        </div>
      </form>

      <form className="panel mb-6 grid gap-4 p-4 md:grid-cols-3" onSubmit={productForm.handleSubmit((values) => addProduct.mutate(values))}>
        <Field label="SKU">
          <Input {...productForm.register("sku", { required: true })} />
        </Field>
        <Field label="Product name">
          <Input {...productForm.register("name", { required: true })} />
        </Field>
        <Field label="Product description">
          <Textarea rows={3} {...productForm.register("description", { required: true })} />
        </Field>
        <div className="md:col-span-3 flex items-center gap-3">
          <Button type="submit" disabled={addProduct.isPending || !can("campaigns.write")}>
            {addProduct.isPending ? "Saving…" : "Add product"}
          </Button>
          {addProduct.isSuccess ? <p className="text-sm text-emerald-700">Product saved.</p> : null}
        </div>
      </form>

      <form
        className="panel mb-6 grid gap-4 p-4"
        onSubmit={generateForm.handleSubmit((values) => generate.mutate(values))}
      >
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Product">
            <Select {...generateForm.register("product_id", { required: true })}>
              <option value="">Select</option>
              {catalog.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Ad network">
            <Select {...generateForm.register("ad_channel")}>
              <option value="linkedin">LinkedIn</option>
              <option value="instagram">Meta</option>
            </Select>
          </Field>
        </div>
        <Field label="What should this say? Optional">
          <Textarea
            rows={3}
            {...generateForm.register("brief")}
            placeholder="Leave this empty and Gemini chooses the angle from the company and product."
          />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={generate.isPending || !can("campaigns.write") || catalog.length === 0}>
            {generate.isPending ? "Drafting…" : "Generate drafts"}
          </Button>
          {generate.isSuccess ? <p className="text-sm text-emerald-700">Drafts are ready to review. Nothing was published.</p> : null}
          {generate.isError ? <p className="text-sm text-red-700">Drafts were not created. Save the company and a product description first.</p> : null}
        </div>
      </form>

      {rows.length === 0 ? (
        <EmptyState title="No drafts" body="Save your company and a product, then generate. A note is optional. Drafts stay here until you publish one." />
      ) : (
        <DataTable
          rows={rows}
          columns={[
            { key: "channel", header: "Channel", cell: (row) => `${labelize(row.channel)} ${labelize(row.kind)}` },
            {
              key: "headline",
              header: "Headline",
              cell: (row) => <Link href={`/content/${row.id}`}>{row.headline || row.body || row.brief}</Link>,
            },
            {
              key: "status",
              header: "Status",
              cell: (row) => <Badge tone={tone(row.status)}>{labelize(row.status)}</Badge>,
            },
            { key: "error", header: "Detail", cell: (row) => row.error || row.destination_url || "—" },
            {
              key: "id",
              header: "",
              cell: (row) =>
                can("campaigns.write") && row.status !== "published" && row.status !== "paused" && row.status !== "mock" ? (
                  <span className="flex gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setEditing(row);
                        draftForm.reset({ headline: row.headline, body: row.body, cta: row.cta, image_url: row.image_url });
                      }}
                    >
                      Edit
                    </Button>
                    <Button type="button" onClick={() => publish.mutate(row.id)} disabled={publish.isPending || (row.status === "failed" && !row.body)}>
                      Publish
                    </Button>
                  </span>
                ) : null,
            },
          ]}
        />
      )}

      <Drawer open={editing !== null} title="Edit draft" onClose={() => setEditing(null)}>
        <form
          onSubmit={draftForm.handleSubmit((values) => {
            if (!editing) return;
            saveDraft.mutate({ ...values, id: editing.id });
          })}
          className="space-y-4"
        >
          <Field label="Headline">
            <Input {...draftForm.register("headline")} />
          </Field>
          <Field label="Body">
            <Textarea rows={6} {...draftForm.register("body", { required: true })} />
          </Field>
          <Field label="Call to action">
            <Input {...draftForm.register("cta")} />
          </Field>
          <Field label="Image URL">
            <Input {...draftForm.register("image_url")} placeholder="Required for Instagram" />
          </Field>
          <FormActions pending={saveDraft.isPending} onCancel={() => setEditing(null)} />
        </form>
      </Drawer>
    </div>
  );
}
