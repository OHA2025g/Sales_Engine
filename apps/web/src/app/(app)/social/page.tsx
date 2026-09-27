"use client";

import { DataTable } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Drawer, Field, FormActions, Input, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { labelize } from "@/lib/format";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

type SocialPost = {
  id: string;
  channel: string;
  body: string;
  link_url: string;
  image_url: string;
  status: string;
  provider: string;
  external_id: string;
  is_mock: boolean;
  error: string;
};

type ChannelStatus = {
  channel: string;
  mode: string;
  configured: boolean;
  missing: string[];
};

type PostForm = { channel: string; body: string; link_url: string; image_url: string };

export default function SocialPostsPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const form = useForm<PostForm>({ defaultValues: { channel: "linkedin", body: "", link_url: "", image_url: "" } });
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
  const create = useMutation({
    mutationFn: (body: PostForm) => api("/api/v1/social/posts", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["social-posts"] });
      setOpen(false);
      form.reset();
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
        subtitle="Text posts for a LinkedIn company page, a Facebook Page, and Instagram. These are not ads. Mock mode records the copy and does not publish it."
        actions={can("campaigns.write") ? <Button onClick={() => setOpen(true)}>New post</Button> : null}
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
      {rows.length === 0 ? (
        <EmptyState title="No posts" body="A post appears here after you save one. Mock posts are not sent to LinkedIn or Meta." />
      ) : (
        <DataTable
          rows={rows}
          columns={[
            { key: "channel", header: "Channel", cell: (row) => labelize(row.channel) },
            { key: "body", header: "Post", cell: (row) => row.body },
            {
              key: "status",
              header: "Status",
              cell: (row) => <Badge tone={row.status === "published" ? "ok" : row.status === "failed" ? "rose" : "gold"}>{labelize(row.status)}</Badge>,
            },
            { key: "error", header: "Detail", cell: (row) => row.error || row.external_id || "—" },
          ]}
        />
      )}
      <Drawer open={open} title="New post" onClose={() => setOpen(false)}>
        <form onSubmit={form.handleSubmit((values) => create.mutate(values))} className="space-y-4">
          <Field label="Channel">
            <Select {...form.register("channel")}>
              <option value="linkedin">LinkedIn</option>
              <option value="facebook">Facebook Page</option>
              <option value="instagram">Instagram</option>
            </Select>
          </Field>
          <Field label="Text"><Textarea rows={5} {...form.register("body", { required: true })} /></Field>
          <Field label="Link"><Input {...form.register("link_url")} placeholder="https://" /></Field>
          <Field label="Image URL"><Input {...form.register("image_url")} placeholder="Required for Instagram" /></Field>
          {create.isError ? <p className="text-sm text-red-700">The post could not be saved.</p> : null}
          <FormActions pending={create.isPending} onCancel={() => setOpen(false)} />
        </form>
      </Drawer>
    </div>
  );
}
