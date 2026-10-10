"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError, api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

type ChannelHit = { rank: number; title: string; url: string; snippet: string };
type ChannelBucket = { channel: string; mode: string; provider: string; reason: string; hits: ChannelHit[] };
type ChannelSearch = {
  id: string;
  query: string;
  status: string;
  provider: string;
  created_at: string;
  channels: ChannelBucket[];
};
type SearchStatus = { provider: string; configured: boolean; detail: string };
type SearchForm = { query: string };

const CHANNELS = [
  { id: "google", label: "Google" },
  { id: "facebook", label: "Facebook" },
  { id: "instagram", label: "Instagram" },
  { id: "linkedin", label: "LinkedIn" },
] as const;

export default function ChannelSearchPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const form = useForm<SearchForm>({ defaultValues: { query: "" } });
  const status = useQuery({
    queryKey: ["channel-search-status"],
    queryFn: async () => (await api<SearchStatus>("/api/v1/channel-search/status")).data,
    enabled: can("campaigns.read"),
  });
  const history = useQuery({
    queryKey: ["channel-searches"],
    queryFn: async () => (await api<ChannelSearch[]>("/api/v1/channel-search")).data ?? [],
    enabled: can("campaigns.read"),
  });
  const search = useMutation({
    mutationFn: (query: string) => api<ChannelSearch>("/api/v1/channel-search", { method: "POST", body: JSON.stringify({ query }) }),
    onSuccess: (envelope) => {
      const created = envelope.data;
      if (created) setSelectedId(created.id);
      void client.invalidateQueries({ queryKey: ["channel-searches"] });
    },
  });

  if (!can("campaigns.read")) return <DeniedState />;
  if (status.isLoading || history.isLoading) return <LoadingState label="Reading channel search" />;
  if (status.isError || history.isError) return <ErrorState message="Channel search could not be loaded." />;

  const rows = history.data ?? [];
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0];
  const source = status.data;

  return (
    <div>
      <PageHeader
        eyebrow="Marketing"
        title="Channel search"
        subtitle="Search a keyword or statement. Google, Facebook, Instagram, and LinkedIn each show up to 10 public results in Google’s rank order."
      />
      {source ? (
        <article className="panel mb-6 p-4">
          <p className="text-xs uppercase tracking-[0.16em] text-brand">{source.configured ? "Live search" : "Not configured"}</p>
          <p className="mt-2 text-sm text-[var(--muted)]">{source.detail}</p>
        </article>
      ) : null}
      {can("campaigns.write") ? (
        <form
          className="panel mb-6 flex flex-col gap-4 p-4 md:flex-row md:items-end"
          onSubmit={form.handleSubmit((values) => search.mutate(values.query))}
        >
          <div className="min-w-0 flex-1">
            <Field label="Keyword or statement">
              <Input placeholder="Example: warehouse automation for mid-size distributors" {...form.register("query", { required: true, minLength: 2 })} />
            </Field>
          </div>
          <Button type="submit" disabled={search.isPending}>
            {search.isPending ? "Searching…" : "Search channels"}
          </Button>
        </form>
      ) : null}
      {search.isPending ? <p className="mb-4 text-sm text-[var(--muted)]">Searching the four channels. This can take up to a minute.</p> : null}
      {search.isError ? (
        <p className="mb-4 text-sm text-red-700">
          {search.error instanceof ApiError ? search.error.message : "The search could not be completed."}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <EmptyState
          title="No searches yet"
          body="Enter a keyword to retrieve the public results Google ranks for that statement on each channel. Nothing is filled in when a source is not connected."
        />
      ) : selected ? (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {rows.map((row) => (
              <Button key={row.id} type="button" variant={row.id === selected.id ? "primary" : "ghost"} onClick={() => setSelectedId(row.id)}>
                {row.query}
              </Button>
            ))}
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {CHANNELS.map((channel) => {
              const bucket = selected.channels.find((item) => item.channel === channel.id);
              return <ChannelCard key={channel.id} label={channel.label} bucket={bucket} />;
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ChannelCard({ label, bucket }: { label: string; bucket: ChannelBucket | undefined }) {
  const hits = bucket?.hits ?? [];
  const mode = bucket?.mode || "failed";
  return (
    <article className="panel p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-medium text-navy">{label}</h2>
        <Badge tone={mode === "live" ? "ok" : mode === "not_configured" ? "gold" : "rose"}>{mode === "live" ? "Ranked" : mode === "not_configured" ? "Not configured" : "Unavailable"}</Badge>
      </div>
      {hits.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">{bucket?.reason || "No public posts were returned for this keyword."}</p>
      ) : (
        <ol className="space-y-3">
          {hits.map((hit) => (
            <li key={`${hit.rank}-${hit.url}`} className="border-t border-[var(--line)] pt-3 first:border-t-0 first:pt-0">
              <p className="text-xs uppercase tracking-[0.14em] text-brand">Rank {hit.rank}</p>
              <a className="mt-1 block font-medium text-navy underline-offset-2 hover:underline" href={hit.url} target="_blank" rel="noreferrer">
                {hit.title}
              </a>
              {hit.snippet ? <p className="mt-1 text-sm text-[var(--muted)]">{hit.snippet}</p> : null}
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
