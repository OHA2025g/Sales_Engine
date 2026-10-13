"use client";

import { DataTable } from "@/components/data-table";
import { FormDesigner, defaultFormFields, type DesignedField, type DesignedForm } from "@/components/form-designer";
import { PostWizard, type WizardSource } from "@/components/post-wizard";
import { PageHeader } from "@/components/page-header";
import { PublishedPostLink } from "@/components/published-post-link";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { labelize } from "@/lib/format";
import { ApiError, api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

type ExtraLink = { label: string; url: string };

type SocialPost = WizardSource & {
  link_url: string;
  extra_links: ExtraLink[];
  form_name: string;
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
  fields?: DesignedField[];
};

type ChannelStatus = {
  channel: string;
  mode: string;
  configured: boolean;
  missing: string[];
};

export default function SocialPostsPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [editing, setEditing] = useState<SocialPost | null>(null);
  const [creating, setCreating] = useState(false);
  const [designing, setDesigning] = useState<DesignedForm | null>(null);
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
  const createForm = useMutation({
    mutationFn: (body: DesignedForm) =>
      api<PublicForm>("/api/v1/acquisition/form-keys", { method: "POST", body: JSON.stringify({ name: body.name, fields: body.fields }) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["public-forms"] });
      setDesigning(null);
    },
  });
  const updateForm = useMutation({
    mutationFn: (body: DesignedForm) =>
      api<PublicForm>(`/api/v1/acquisition/form-keys/${body.id}`, { method: "PATCH", body: JSON.stringify({ name: body.name, fields: body.fields }) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["public-forms"] });
      setDesigning(null);
    },
  });
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
            <Button type="button" onClick={() => setDesigning({ name: "", fields: defaultFormFields() })}>
              Create form
            </Button>
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
                  <span className="flex flex-wrap gap-3">
                    {can("acquisition.write") && row.status === "active" ? (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setDesigning({ id: row.id, name: row.name, fields: row.fields?.length ? row.fields : defaultFormFields() })}
                      >
                        Design
                      </Button>
                    ) : null}
                    {row.url && row.status === "active" ? (
                      <a className="text-brand" href={row.url} target="_blank" rel="noreferrer">
                        Open form
                      </a>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
      {rows.length === 0 ? (
        <EmptyState title="No posts" body="Save a post and it waits in Approvals. It is posted only after someone approves it." />
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
      {creating || editing ? (
        <PostWizard
          forms={forms.data ?? []}
          source={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onSaved={() => {
            void client.invalidateQueries({ queryKey: ["social-posts"] });
            void client.invalidateQueries({ queryKey: ["approvals"] });
          }}
        />
      ) : null}
      {designing ? (
        <FormDesigner
          initial={designing}
          pending={createForm.isPending || updateForm.isPending}
          error={
            createForm.isError
              ? createForm.error instanceof ApiError
                ? createForm.error.message
                : "The form could not be created."
              : updateForm.isError
                ? updateForm.error instanceof ApiError
                  ? updateForm.error.message
                  : "The form could not be saved."
                : ""
          }
          onClose={() => setDesigning(null)}
          onSave={(value) => {
            if (value.id) updateForm.mutate(value);
            else createForm.mutate(value);
          }}
        />
      ) : null}
    </div>
  );
}
