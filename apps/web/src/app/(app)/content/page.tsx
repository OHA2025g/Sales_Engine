"use client";

import { PageHeader } from "@/components/page-header";
import { PublishedPostLink } from "@/components/published-post-link";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Field, FormActions, Input, Select, Textarea } from "@/components/ui";
import { MetricStrip } from "@/components/workspace-ui";
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
  permalink: string;
  external_id: string;
};

type ProfileForm = Omit<Profile, "id">;
type ProductForm = { sku: string; name: string; description: string };
type GenerateForm = { product_id: string; ad_channel: string; brief: string };
type DraftForm = { headline: string; body: string; cta: string; image_url: string };
type StudioTab = "company" | "products" | "generate" | "drafts" | "edit" | "preview" | "publish" | "view";

const STUDIO_TABS: { id: StudioTab; label: string }[] = [
  { id: "company", label: "1 Company" },
  { id: "products", label: "2 Products" },
  { id: "generate", label: "3 Generate" },
  { id: "drafts", label: "4 Drafts" },
  { id: "edit", label: "5 Edit" },
  { id: "preview", label: "6 Preview" },
  { id: "publish", label: "7 Publish" },
  { id: "view", label: "8 View post" },
];

const PREVIEW_ORDER = ["linkedin", "facebook", "instagram"];

function tone(status: string): "ok" | "rose" | "gold" {
  if (status === "published" || status === "paused") return "ok";
  if (status === "failed") return "rose";
  return "gold";
}

function canRevise(status: string) {
  return status !== "published" && status !== "paused" && status !== "mock";
}

function channelName(channel: string): string {
  if (channel === "linkedin") return "LinkedIn";
  if (channel === "facebook") return "Facebook";
  if (channel === "instagram") return "Instagram";
  return labelize(channel);
}

function previewTitle(row: Draft): string {
  const name = channelName(row.channel);
  return row.kind === "ad" ? `${name} ad` : name;
}

function httpsUrl(url: string): string {
  const value = url.trim();
  return value.startsWith("https://") ? value : "";
}

function hostLabel(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function postedText(row: Draft): string {
  return [row.headline, row.body, row.cta]
    .map((part) => part.trim())
    .filter(Boolean)
    .join("\n\n");
}

function draftsToPreview(rows: Draft[]): Draft[] {
  return rows.slice().sort((left, right) => {
    const leftAd = left.kind === "ad" ? 1 : 0;
    const rightAd = right.kind === "ad" ? 1 : 0;
    if (leftAd !== rightAd) return leftAd - rightAd;
    const leftIndex = PREVIEW_ORDER.indexOf(left.channel);
    const rightIndex = PREVIEW_ORDER.indexOf(right.channel);
    return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
  });
}

function ChannelPreview({ row, company }: { row: Draft; company: string }) {
  const image = httpsUrl(row.image_url);
  const link = httpsUrl(row.destination_url);
  const missingImage = row.channel === "instagram" && row.kind !== "ad" && !image;
  const message = row.kind === "ad" ? row.body.trim() : postedText(row);
  return (
    <article className={`channel-preview channel-${row.channel}`}>
      <header className="channel-preview-head">
        <span>{previewTitle(row)}</span>
        <Badge tone={tone(row.status)}>{labelize(row.status)}</Badge>
      </header>
      <div className="channel-preview-author">
        <span className="channel-preview-mark" aria-hidden="true">
          {(company || "C").slice(0, 1).toUpperCase()}
        </span>
        <div>
          <strong>{company || "Your company"}</strong>
          <p>{row.kind === "ad" ? "Sponsored" : "Organic post"}</p>
        </div>
      </div>
      {image ? <img className="channel-preview-image" src={image} alt={row.headline || previewTitle(row)} /> : null}
      {missingImage ? <p className="channel-preview-gap">Instagram needs a public image URL before this can be posted.</p> : null}
      <div className="channel-preview-copy">
        {row.kind === "ad" && row.headline ? <h3>{row.headline}</h3> : null}
        {message ? <p>{message}</p> : <p className="channel-preview-gap">This draft has no text yet.</p>}
        {row.kind === "ad" && row.cta ? <p className="channel-preview-cta">{row.cta}</p> : null}
      </div>
      {link ? (
        <div className="channel-preview-link">
          <span>{hostLabel(link)}</span>
          <strong>{row.headline || link}</strong>
        </div>
      ) : null}
    </article>
  );
}

function groupDrafts(rows: Draft[]) {
  const groups: { key: string; rows: Draft[] }[] = [];
  for (const row of rows) {
    const key = row.channel || row.kind || "draft";
    const existing = groups.find((group) => group.key === key);
    if (existing) existing.rows.push(row);
    else groups.push({ key, rows: [row] });
  }
  return groups;
}

export default function ContentPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [tab, setTab] = useState<StudioTab>("company");
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
    mutationFn: (body: GenerateForm) => api<Draft[]>("/api/v1/content/generate", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      generateForm.setValue("brief", "");
      setTab("drafts");
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
  const groups = groupDrafts(rows);
  const generated = generate.data?.data ?? [];
  const generationFailed = generate.isSuccess && generated.length > 0 && generated.every((row) => row.status === "failed");
  const writable = can("campaigns.write");
  const ready = rows.filter((row) => canRevise(row.status) && row.status !== "failed").length;
  const published = rows.filter((row) => row.status === "published" || row.status === "paused").length;
  const failed = rows.filter((row) => row.status === "failed").length;

  const editable = rows.filter((row) => canRevise(row.status));
  const previews = draftsToPreview(rows);
  const companyName = saved?.company_name?.trim() || "";
  const publishable = editable;
  const viewable = rows.filter((row) => row.status === "published");

  function openEditor(row: Draft) {
    setEditing(row);
    draftForm.reset({ headline: row.headline, body: row.body, cta: row.cta, image_url: row.image_url });
    setTab("edit");
  }

  function panel(current: StudioTab) {
    switch (current) {
      case "company":
        return (
          <form className="panel" onSubmit={profileForm.handleSubmit((values) => saveProfile.mutate(values))}>
            <header className="panel-head">
              <h2>Company</h2>
            </header>
            <div className="panel-body">
              <div className="content-form">
                <Field label="Company name">
                  <Input {...profileForm.register("company_name", { required: true })} />
                </Field>
                <Field label="Who you sell to">
                  <Input {...profileForm.register("audience")} />
                </Field>
                <div className="span-2">
                  <Field label="What you do">
                    <Textarea rows={4} {...profileForm.register("summary", { required: true })} />
                  </Field>
                </div>
                <div className="span-2">
                  <Field label="Proof you are willing to claim">
                    <Textarea rows={4} {...profileForm.register("proof")} />
                  </Field>
                </div>
                <Field label="Website">
                  <Input {...profileForm.register("website")} placeholder="https://" />
                </Field>
                <Field label="Lead capture link">
                  <Input {...profileForm.register("capture_url")} placeholder="https://your-host/capture/…" />
                </Field>
              </div>
              {saveProfile.isSuccess ? <p className="mt-3 text-sm text-emerald-700">Company saved.</p> : null}
              <div className="sticky-action">
                <Button type="submit" disabled={saveProfile.isPending || !writable}>
                  {saveProfile.isPending ? "Saving…" : "Save company"}
                </Button>
              </div>
            </div>
          </form>
        );
      case "products":
        return (
          <section className="panel">
            <header className="panel-head">
              <h2>Products</h2>
            </header>
            {catalog.length === 0 ? (
              <p className="px-5 pt-4 text-sm text-[var(--muted)]">No products yet. Add one before generating drafts.</p>
            ) : (
              <ul>
                {catalog.map((row) => (
                  <li className="row" key={row.id}>
                    <div className="main">
                      <h3>{row.name}</h3>
                      <p className="connection-note">
                        {row.sku}
                        {row.kind ? ` · ${labelize(row.kind)}` : ""}
                        {row.list_price ? ` · ${row.list_price} ${row.currency}` : ""}
                      </p>
                      {row.description ? <p className="connection-note">{row.description}</p> : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <form className="panel-body" onSubmit={productForm.handleSubmit((values) => addProduct.mutate(values))}>
              <div className="content-form">
                <Field label="SKU">
                  <Input {...productForm.register("sku", { required: true })} />
                </Field>
                <Field label="Product name">
                  <Input {...productForm.register("name", { required: true })} />
                </Field>
                <div className="span-2">
                  <Field label="Product description">
                    <Textarea rows={3} {...productForm.register("description", { required: true })} />
                  </Field>
                </div>
              </div>
              {addProduct.isSuccess ? <p className="mt-3 text-sm text-emerald-700">Product saved.</p> : null}
              <div className="sticky-action">
                <Button type="submit" disabled={addProduct.isPending || !writable}>
                  {addProduct.isPending ? "Saving…" : "Add product"}
                </Button>
              </div>
            </form>
          </section>
        );
      case "generate":
        return (
          <form className="panel" onSubmit={generateForm.handleSubmit((values) => generate.mutate(values))}>
            <header className="panel-head">
              <h2>Generate drafts</h2>
            </header>
            <div className="panel-body">
              <div className="content-form">
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
                <div className="span-2">
                  <Field label="What should this say? Optional">
                    <Textarea
                      rows={3}
                      {...generateForm.register("brief")}
                      placeholder="Leave this empty and Gemini chooses the angle from the company and product."
                    />
                  </Field>
                </div>
              </div>
              {generationFailed ? (
                <p className="mt-3 text-sm text-red-700">{generated[0]?.error || "Drafts were not written. Nothing was published."}</p>
              ) : generate.isSuccess ? (
                <p className="mt-3 text-sm text-emerald-700">Drafts are ready to review. Nothing was published.</p>
              ) : null}
              {generate.isError ? <p className="mt-3 text-sm text-red-700">Drafts were not created. Save the company and a product description first.</p> : null}
              <div className="sticky-action">
                <Button type="submit" disabled={generate.isPending || !writable || catalog.length === 0}>
                  {generate.isPending ? "Drafting…" : "Generate drafts"}
                </Button>
              </div>
            </div>
          </form>
        );
      case "drafts":
        return (
          <section className="panel">
            <header className="panel-head">
              <h2>Drafts</h2>
            </header>
            {rows.length === 0 ? (
              <EmptyState title="No drafts" body="Save the company and a product, then generate. Drafts stay here until you publish one." />
            ) : (
              groups.map((group) => (
                <div key={group.key}>
                  <p className="px-5 pt-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{labelize(group.key)}</p>
                  <ul>
                    {group.rows.map((row) => (
                      <li className="row" key={row.id}>
                        <Link className="main" href={`/content/${row.id}`}>
                          <h3>{row.headline || "Untitled asset"}</h3>
                          <p className="connection-note">
                            {labelize(row.kind)}
                            {row.brief ? ` · ${row.brief}` : row.cta ? ` · ${row.cta}` : ""}
                          </p>
                          {row.error ? <p className="connection-note connection-error">{row.error}</p> : null}
                        </Link>
                        <div className="row-actions">
                          <Badge tone={tone(row.status)}>{labelize(row.status)}</Badge>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))
            )}
          </section>
        );
      case "edit":
        return (
          <section className="panel">
            <header className="panel-head">
              <h2>Edit</h2>
            </header>
            {editable.length === 0 ? (
              <EmptyState title="Nothing to edit" body="Generate a draft first. Published posts stay as they were sent." />
            ) : (
              <ul>
                {editable.map((row) => (
                  <li className="row" key={row.id}>
                    <div className="main">
                      <h3>{row.headline || "Untitled asset"}</h3>
                      <p className="connection-note">
                        {labelize(row.channel)} · {labelize(row.kind)}
                        {row.cta ? ` · ${row.cta}` : ""}
                      </p>
                    </div>
                    <div className="row-actions">
                      <Badge tone={tone(row.status)}>{labelize(row.status)}</Badge>
                      {writable ? (
                        <Button type="button" variant="ghost" onClick={() => openEditor(row)}>
                          Edit
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {editing && writable ? (
              <form
                className="panel-body space-y-4"
                onSubmit={draftForm.handleSubmit((values) => {
                  saveDraft.mutate({ ...values, id: editing.id });
                })}
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
                {saveDraft.isSuccess ? <p className="text-sm text-emerald-700">Draft saved. Nothing was published.</p> : null}
                <FormActions pending={saveDraft.isPending} onCancel={() => setEditing(null)} />
              </form>
            ) : null}
          </section>
        );
      case "preview":
        return (
          <section className="panel">
            <header className="panel-head">
              <h2>Preview</h2>
            </header>
            {previews.length === 0 ? (
              <EmptyState title="Nothing to preview" body="Generate drafts first. Each channel appears here before anything is published." />
            ) : (
              <>
                <p className="px-5 pt-4 text-sm text-[var(--muted)]">This is the post each channel will carry. Nothing is sent from this step.</p>
                <div className="preview-grid">
                  {previews.map((row) => (
                    <ChannelPreview key={row.id} row={row} company={companyName} />
                  ))}
                </div>
                <div className="preview-next">
                  <Button type="button" onClick={() => setTab("publish")}>
                    Continue to publish
                  </Button>
                </div>
              </>
            )}
          </section>
        );
      case "publish":
        return (
          <section className="panel">
            <header className="panel-head">
              <h2>Publish</h2>
            </header>
            {publishable.length === 0 ? (
              <EmptyState title="Nothing to publish" body="Drafts that are still in review appear here. A published draft is not sent again." />
            ) : (
              <ul>
                {publishable.map((row) => (
                  <li className="row" key={row.id}>
                    <div className="main">
                      <h3>{row.headline || "Untitled asset"}</h3>
                      <p className="connection-note">
                        {labelize(row.channel)} · {labelize(row.kind)}
                      </p>
                      {row.error ? <p className="connection-note connection-error">{row.error}</p> : null}
                    </div>
                    <div className="row-actions">
                      <Badge tone={tone(row.status)}>{labelize(row.status)}</Badge>
                      {writable ? (
                        <Button type="button" onClick={() => publish.mutate(row.id)} disabled={publish.isPending || (row.status === "failed" && !row.body)}>
                          Publish
                        </Button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      case "view":
        return (
          <section className="panel">
            <header className="panel-head">
              <h2>View post</h2>
            </header>
            {viewable.length === 0 ? (
              <EmptyState title="No live post" body="Publish a draft first. The live link opens here after Facebook, Instagram, or LinkedIn accepts it." />
            ) : (
              <ul>
                {viewable.map((row) => (
                  <li className="row" key={row.id}>
                    <div className="main">
                      <h3>{row.headline || "Untitled asset"}</h3>
                      <p className="connection-note">
                        {labelize(row.channel)} · {labelize(row.kind)}
                      </p>
                    </div>
                    <div className="row-actions">
                      <PublishedPostLink href={row.permalink} status={row.status} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      default: {
        const exhaustive: never = current;
        return exhaustive;
      }
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Create"
        title="Content"
        subtitle="Work the tabs in order. Gemini writes the posts and the ad from your company and product. Nothing goes out until you publish it."
      />
      <div className="stack">
        <MetricStrip
          items={[
            { label: "Ready to review", value: String(ready) },
            { label: "Published", value: String(published) },
            { label: "Failed", value: String(failed) },
            { label: "Products", value: String(catalog.length) },
          ]}
        />
        <div className="studio-tabs" role="tablist" aria-label="Content studio">
          {STUDIO_TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`studio-tab-${item.id}`}
              aria-selected={tab === item.id}
              aria-controls={`studio-panel-${item.id}`}
              tabIndex={tab === item.id ? 0 : -1}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`studio-panel-${tab}`} aria-labelledby={`studio-tab-${tab}`}>
          {panel(tab)}
        </div>
      </div>
    </div>
  );
}
