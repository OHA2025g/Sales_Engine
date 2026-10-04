"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Button, Field, Input, Textarea } from "@/components/ui";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type Draft = {
  id: string;
  channel: string;
  headline: string;
  body: string;
  cta: string;
  status: string;
  error: string;
};

export default function ContentEditorPage() {
  const params = useParams<{ id: string }>();
  const { can } = useAuth();
  const client = useQueryClient();
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [cta, setCta] = useState("");
  const [notice, setNotice] = useState("");
  const query = useQuery({
    queryKey: ["content-drafts"],
    queryFn: async () => (await api<Draft[]>("/api/v1/content/drafts")).data ?? [],
    enabled: can("campaigns.read"),
  });
  const draft = (query.data ?? []).find((row) => row.id === params.id);
  useEffect(() => {
    if (!draft) return;
    setHeadline(draft.headline);
    setBody(draft.body);
    setCta(draft.cta);
  }, [draft]);
  const save = useMutation({
    mutationFn: () =>
      api(`/api/v1/content/drafts/${params.id}`, {
        method: "PATCH",
        body: JSON.stringify({ headline, body, cta }),
      }),
    onSuccess: () => {
      setNotice("Draft saved. Publishing still needs an approved campaign budget.");
      void client.invalidateQueries({ queryKey: ["content-drafts"] });
    },
    onError: (error: Error) => setNotice(error.message),
  });
  if (!can("campaigns.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Opening the draft" />;
  if (query.isError) return <ErrorState message="Drafts could not be loaded." />;
  if (!draft) return <ErrorState message="This draft is not in the tenant." />;
  return (
    <div>
      <PageHeader
        eyebrow="Marketing"
        title={draft.headline || "Content editor"}
        subtitle={`${draft.channel} draft. Editing does not publish.`}
        nextHref="/calendar"
        nextLabel="Calendar"
      />
      <div className="mb-4">
        <StatusPill tone={draft.status === "published" ? "success" : draft.status === "failed" ? "blocked" : "review"}>{draft.status}</StatusPill>
      </div>
      <form
        className="panel max-w-3xl space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Headline"><Input value={headline} onChange={(event) => setHeadline(event.target.value)} /></Field>
        <Field label="Body"><Textarea rows={8} value={body} onChange={(event) => setBody(event.target.value)} /></Field>
        <Field label="Call to action"><Input value={cta} onChange={(event) => setCta(event.target.value)} /></Field>
        {draft.error ? <p className="text-sm text-[var(--rose)]">{draft.error}</p> : null}
        {can("campaigns.write") ? <Button type="submit" disabled={save.isPending}>Save draft</Button> : null}
        {notice ? <p className="text-sm text-[var(--muted)]">{notice}</p> : null}
      </form>
    </div>
  );
}
