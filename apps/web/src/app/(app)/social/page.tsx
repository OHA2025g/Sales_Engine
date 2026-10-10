"use client";

import { DataTable } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { PublishedPostLink } from "@/components/published-post-link";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Drawer, Field, FormActions, Input, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { labelize } from "@/lib/format";
import { ApiError, api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent } from "react";
import { useFieldArray, useForm } from "react-hook-form";

type ExtraLink = { label: string; url: string };

type SocialPost = {
  id: string;
  channel: string;
  body: string;
  link_url: string;
  image_url: string;
  extra_links: ExtraLink[];
  form_key_id: string | null;
  form_name: string;
  status: string;
  provider: string;
  external_id: string;
  permalink: string;
  is_mock: boolean;
  error: string;
};

type PublicForm = {
  id: string;
  name: string;
  status: string;
  url: string;
};

type ChannelStatus = {
  channel: string;
  mode: string;
  configured: boolean;
  missing: string[];
};

type PostForm = {
  channel: string;
  body: string;
  link_url: string;
  image_url: string;
  form_key_id: string;
  extra_links: ExtraLink[];
};

function blankPost(): PostForm {
  return { channel: "linkedin", body: "", link_url: "", image_url: "", form_key_id: "", extra_links: [{ label: "", url: "" }] };
}

function postBody(body: PostForm) {
  return {
    channel: body.channel,
    body: body.body,
    image_url: body.image_url,
    link_url: body.form_key_id ? "" : body.link_url,
    form_key_id: body.form_key_id || null,
    extra_links: body.extra_links
      .map((item) => ({ label: item.label.trim(), url: item.url.trim() }))
      .filter((item) => item.label || item.url),
  };
}
type NewForm = { name: string };
type SocialDraft = { channel: string; body: string; link_url: string };

export default function SocialPostsPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<SocialPost | null>(null);
  const form = useForm<PostForm>({ defaultValues: blankPost() });
  const extraLinks = useFieldArray({ control: form.control, name: "extra_links" });
  const newForm = useForm<NewForm>({ defaultValues: { name: "" } });
  const selectedFormId = form.watch("form_key_id");
  const channel = form.watch("channel");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const posts = useQuery({
    queryKey: ["social-posts"],
    queryFn: async () => (await api<SocialPost[]>("/api/v1/social/posts")).data ?? [],
    enabled: can("campaigns.read"),
  });
  const status = useQuery({
    queryKey: ["social-status"],
    queryFn: async () => (await api<ChannelStatus[]>("/api/v1/social/status")).data ?? [],
    enabled: can("campaigns.read"),
  });
  const forms = useQuery({
    queryKey: ["public-forms"],
    queryFn: async () => (await api<PublicForm[]>("/api/v1/acquisition/form-keys")).data ?? [],
    enabled: can("acquisition.read"),
  });
  const draft = useMutation({
    mutationFn: (channel: string) =>
      api<SocialDraft>("/api/v1/social/draft", { method: "POST", body: JSON.stringify({ channel }) }),
    onSuccess: (envelope) => {
      const written = envelope.data;
      if (!written) return;
      form.setValue("body", written.body, { shouldValidate: true });
      if (written.link_url && !form.getValues("form_key_id")) form.setValue("link_url", written.link_url);
    },
  });
  const createForm = useMutation({
    mutationFn: (body: NewForm) => api<PublicForm>("/api/v1/acquisition/form-keys", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (envelope) => {
      void client.invalidateQueries({ queryKey: ["public-forms"] });
      newForm.reset();
      if (envelope.data?.id) form.setValue("form_key_id", envelope.data.id);
    },
  });
  const create = useMutation({
    mutationFn: (body: PostForm) =>
      api("/api/v1/social/posts", {
        method: "POST",
        body: JSON.stringify(postBody(body)),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["social-posts"] });
      setCreating(false);
      setEditing(null);
      form.reset(blankPost());
    },
  });
  const update = useMutation({
    mutationFn: (body: PostForm & { id: string }) =>
      api(`/api/v1/social/posts/${body.id}`, {
        method: "PATCH",
        body: JSON.stringify(postBody(body)),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["social-posts"] });
      setEditing(null);
      form.reset(blankPost());
    },
  });

  async function uploadImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploadError("");
    setUploading(true);
    try {
      const body = new FormData();
      body.set("file", file);
      const saved = await api<{ url: string }>("/api/v1/social/images", { method: "POST", body });
      if (saved.data?.url) form.setValue("image_url", saved.data.url);
    } catch (error) {
      setUploadError(error instanceof ApiError ? error.message : "The image could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  const liveCaptionOnly = editing !== null && editing.status === "published" && editing.channel !== "instagram";
  const replaceInstagram = editing !== null && editing.status === "published" && editing.channel === "instagram";

  function closeDrawer() {
    setCreating(false);
    setEditing(null);
  }

  if (!can("campaigns.read")) return <DeniedState />;
  if (posts.isLoading || status.isLoading) return <LoadingState label="Reading social posts" />;
  if (posts.isError || status.isError) return <ErrorState message="Social posts could not be loaded." />;
  const rows = posts.data ?? [];
  const channels = status.data ?? [];

  return (
    <div>
      <PageHeader
        eyebrow="Organic"
        title="Social posts"
        subtitle="Text posts for a LinkedIn company page, a Facebook Page, and Instagram. Choose a form and its link is attached. Add any other links, such as your website, and they are written into the post."
        actions={
          can("campaigns.write") ? (
            <Button
              onClick={() => {
                setEditing(null);
                form.reset(blankPost());
                setCreating(true);
              }}
            >
              New post
            </Button>
          ) : null
        }
      />
      <div className="mb-6 grid gap-3 md:grid-cols-3">
        {channels.map((row) => (
          <article key={row.channel} className="panel p-4">
            <p className="text-sm font-medium text-navy">{labelize(row.channel)}</p>
            <p className="mt-1 text-xs uppercase tracking-[0.16em] text-brand">{labelize(row.mode)}</p>
            {row.mode !== "mock" && row.missing.length > 0 ? (
              <p className="mt-2 text-sm text-[var(--muted)]">Still needed: {row.missing.join(", ")}</p>
            ) : null}
          </article>
        ))}
      </div>
      {can("acquisition.read") ? (
        <section className="panel mb-6 space-y-4 p-4">
          <div>
            <h2 className="text-lg font-semibold text-navy">Forms</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              Create one form for each purpose, such as a demo request or a partnership inquiry. The post uses the form you select.
            </p>
          </div>
          {can("acquisition.write") ? (
            <form className="flex flex-wrap items-end gap-3" onSubmit={newForm.handleSubmit((values) => createForm.mutate(values))}>
              <Field label="Form purpose">
                <Input {...newForm.register("name", { required: true })} placeholder="Demo request" />
              </Field>
              <Button type="submit" disabled={createForm.isPending}>
                {createForm.isPending ? "Creating…" : "Create form"}
              </Button>
            </form>
          ) : null}
          {createForm.isError ? (
            <p className="text-sm text-red-700">
              {createForm.error instanceof ApiError ? createForm.error.message : "The form could not be created."}
            </p>
          ) : null}
          {(forms.data ?? []).length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No forms yet.</p>
          ) : (
            <ul className="space-y-2">
              {(forms.data ?? []).map((row) => (
                <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  <span>
                    {row.name} <span className="text-[var(--muted)]">· {labelize(row.status)}</span>
                  </span>
                  {row.url && row.status === "active" ? (
                    <a className="text-brand" href={row.url} target="_blank" rel="noreferrer">
                      Open form
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
      {rows.length === 0 ? (
        <EmptyState title="No posts" body="A post appears here after you save one. Mock posts are not sent to LinkedIn or Meta." />
      ) : (
        <DataTable
          rows={rows}
          columns={[
            { key: "channel", header: "Channel", cell: (row) => labelize(row.channel) },
            { key: "body", header: "Post", cell: (row) => row.body },
            { key: "form_name", header: "Form", cell: (row) => row.form_name || "—" },
            {
              key: "extra_links",
              header: "Other links",
              cell: (row) =>
                row.extra_links?.length
                  ? row.extra_links.map((item) => (item.label ? `${item.label}: ${item.url}` : item.url)).join(" · ")
                  : "—",
            },
            {
              key: "status",
              header: "Status",
              cell: (row) => <Badge tone={row.status === "published" ? "ok" : row.status === "failed" ? "rose" : "gold"}>{labelize(row.status)}</Badge>,
            },
            { key: "error", header: "Detail", cell: (row) => row.error || "—" },
            {
              key: "permalink",
              header: "",
              cell: (row) => (
                <span className="flex flex-wrap gap-2">
                  <PublishedPostLink href={row.permalink} status={row.status} />
                  {can("campaigns.write") ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setCreating(false);
                        form.reset({
                          channel: row.channel,
                          body: row.body,
                          link_url: row.form_key_id ? "" : row.link_url,
                          image_url: row.image_url,
                          form_key_id: row.form_key_id ?? "",
                          extra_links: row.extra_links?.length ? row.extra_links : [{ label: "", url: "" }],
                        });
                        setEditing(row);
                      }}
                    >
                      Edit
                    </Button>
                  ) : null}
                </span>
              ),
            },
          ]}
        />
      )}
      <Drawer open={creating || editing !== null} title={editing ? "Edit post" : "New post"} onClose={closeDrawer}>
        <form
          onSubmit={form.handleSubmit((values) => {
            if (replaceInstagram && editing) {
              create.mutate({ ...values, channel: editing.channel });
              return;
            }
            if (editing) {
              update.mutate({ ...values, id: editing.id });
              return;
            }
            create.mutate(values);
          })}
          className="space-y-4"
        >
          <Field label="Channel">
            {editing ? (
              <Input value={labelize(editing.channel)} disabled />
            ) : (
              <Select {...form.register("channel")}>
                <option value="linkedin">LinkedIn</option>
                <option value="facebook">Facebook Page</option>
                <option value="instagram">Instagram</option>
              </Select>
            )}
          </Field>
          {replaceInstagram ? (
            <p className="text-sm text-[var(--muted)]">
              Instagram does not let an app change a post that is already live. This publishes a new post. The one already on Instagram stays as it is.
            </p>
          ) : null}
          {liveCaptionOnly ? (
            <p className="text-sm text-[var(--muted)]">
              Save updates the caption on the live post. Other links are written into that caption. The photo and the form link stay as they were first published.
            </p>
          ) : null}
          <Field label="Text">
            <Textarea rows={5} {...form.register("body", { required: true })} />
          </Field>
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              disabled={draft.isPending || !can("campaigns.write")}
              onClick={() => draft.mutate(form.getValues("channel"))}
            >
              {draft.isPending ? "Drafting…" : "Draft with Gemini"}
            </Button>
            <p className="text-sm text-[var(--muted)]">
              {editing ? "Gemini rewrites the text. Save applies it to this post." : "Gemini writes the text. Save is what publishes it."}
            </p>
          </div>
          {draft.isError ? (
            <p className="text-sm text-red-700">
              {draft.error instanceof ApiError ? draft.error.message : "Gemini did not return a draft. Nothing was published."}
            </p>
          ) : null}
          {can("acquisition.read") && !liveCaptionOnly ? (
            <Field label="Form">
              <Select {...form.register("form_key_id")}>
                <option value="">No form</option>
                {(forms.data ?? [])
                  .filter((row) => row.status === "active" && row.url)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
              </Select>
            </Field>
          ) : null}
          {liveCaptionOnly ? (
            <p className="text-sm text-[var(--muted)]">Form on this post: {editing?.form_name || "none"}.</p>
          ) : selectedFormId ? (
            <p className="text-sm text-[var(--muted)]">
              {channel === "instagram"
                ? "Instagram cannot place a form on the photo. The form link is written at the top of the caption so people can open it and fill it in."
                : `This post will link to ${(forms.data ?? []).find((row) => row.id === selectedFormId)?.name || "that form"}. People who open it can fill it in.`}
            </p>
          ) : (
            <Field label="Link"><Input {...form.register("link_url")} placeholder="https://" /></Field>
          )}
          <div className="space-y-3">
            <div>
              <p className="text-sm font-medium text-navy">Other links</p>
              <p className="mt-1 text-sm text-[var(--muted)]">
                Add your website or any other address. Each one is written into the post. The form stays the link people open to fill it in.
              </p>
            </div>
            {extraLinks.fields.map((field, index) => (
              <div key={field.id} className="space-y-2">
                <Field label="Name">
                  <Input {...form.register(`extra_links.${index}.label`)} placeholder="Website" />
                </Field>
                <Field label="Address">
                  <Input {...form.register(`extra_links.${index}.url`)} placeholder="https://" />
                </Field>
                {extraLinks.fields.length > 1 ? (
                  <Button type="button" variant="ghost" onClick={() => extraLinks.remove(index)}>
                    Remove
                  </Button>
                ) : null}
              </div>
            ))}
            <Button
              type="button"
              variant="ghost"
              disabled={extraLinks.fields.length >= 8}
              onClick={() => extraLinks.append({ label: "", url: "" })}
            >
              Add another link
            </Button>
          </div>
          {liveCaptionOnly ? null : (
            <>
              <Field label="Image URL">
                <Input {...form.register("image_url")} placeholder="https:// — or upload a file below" />
              </Field>
              <Field label="Upload image">
                <Input type="file" accept="image/jpeg,image/png" onChange={uploadImage} />
              </Field>
              <p className="text-sm text-[var(--muted)]">
                {uploading ? "Uploading…" : "Paste a public image link, or upload a JPEG or PNG. Instagram needs one of these."}
              </p>
            </>
          )}
          {uploadError ? <p className="text-sm text-red-700">{uploadError}</p> : null}
          {create.isError ? (
            <p className="text-sm text-red-700">
              {create.error instanceof ApiError ? create.error.message : "The post could not be saved."}
            </p>
          ) : null}
          {update.isError ? (
            <p className="text-sm text-red-700">
              {update.error instanceof ApiError ? update.error.message : "The post could not be updated."}
            </p>
          ) : null}
          <FormActions
            pending={create.isPending || update.isPending}
            onCancel={closeDrawer}
            label={replaceInstagram ? "Publish new post" : "Save"}
          />
        </form>
      </Drawer>
    </div>
  );
}
