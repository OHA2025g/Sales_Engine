"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, Field, Input } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ApiError, api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
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

const STOPWORDS = new Set([
  "a", "an", "and", "or", "the", "for", "of", "to", "in", "on", "with", "by", "from", "at", "is", "it", "this", "that",
  "your", "our", "how", "what", "why", "when", "where", "who", "be", "as", "are", "was", "into", "about",
]);

type HitView = {
  label: string;
  hit: ChannelHit;
  query: string;
  provider: string;
  mode: string;
  searchedAt: string;
  displayRank: number;
};

const ENGAGEMENT_BAIT = /\b(quiz|tag a friend|comment (yes|below|if)|like if|share if)\b/i;
const OFFER = /\b(course|diploma|program|programme|certification|enroll|enrol|admission|syllabus|mba|degree|pgdm|placement)\b/i;

function queryTokens(query: string) {
  const seen = new Set<string>();
  const tokens: string[] = [];
  for (const token of query.toLowerCase().match(/[a-z0-9]+/g) ?? []) {
    if (token.length < 2 || STOPWORDS.has(token) || seen.has(token)) continue;
    seen.add(token);
    tokens.push(token);
  }
  return tokens;
}

function termsIn(text: string, tokens: string[]) {
  const lowered = text.toLowerCase();
  return tokens.filter((token) => new RegExp(`\\b${token}\\b`, "i").test(lowered));
}

function isMeta(label: string) {
  return label === "Facebook" || label === "Instagram";
}

function wordList(words: string[]) {
  if (words.length <= 1) return words[0] ?? "";
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

function plainCreative(value: string) {
  return [...value]
    .map((char) => {
      const code = char.codePointAt(0) ?? 0;
      if (code >= 0x1d400 && code <= 0x1d419) return String.fromCharCode(65 + code - 0x1d400);
      if (code >= 0x1d41a && code <= 0x1d433) return String.fromCharCode(97 + code - 0x1d41a);
      if (code >= 0x1d5d4 && code <= 0x1d5ed) return String.fromCharCode(65 + code - 0x1d5d4);
      if (code >= 0x1d5ee && code <= 0x1d607) return String.fromCharCode(97 + code - 0x1d5ee);
      return char;
    })
    .join("");
}

function metaScore(query: string, hit: ChannelHit) {
  const tokens = queryTokens(query);
  const text = plainCreative(`${hit.title} ${hit.snippet}`);
  const matched = termsIn(text, tokens);
  const bait = ENGAGEMENT_BAIT.test(text);
  const specific = OFFER.test(text);
  const relevance = tokens.length === 0 ? 0 : matched.length / tokens.length;
  let quality = 1;
  if (specific && !bait) quality += 0.6;
  if (hit.snippet.trim().length >= 80 && !bait) quality += 0.2;
  if (bait) quality -= 0.8;
  return { matched, bait, specific, relevance, score: relevance * Math.max(quality, 0.15) };
}

function rankingParameter(query: string, hit: ChannelHit, label: string) {
  if (!isMeta(label)) {
    const matched = termsIn(`${hit.title} ${hit.snippet}`, queryTokens(query));
    if (matched.length === 0) return "Google organic position";
    return `Google organic position · matched ${matched.join(", ")}`;
  }
  const { matched, bait, specific, relevance } = metaScore(query, hit);
  if (bait) return "Ad quality · engagement bait";
  if (specific && relevance === 1) return "Interest relevance · specific offer";
  if (specific && matched.length > 0) return "Interest relevance · offer named";
  if (matched.length > 0) return `Interest relevance · ${matched.join(", ")}`;
  return "Interest relevance · weak match";
}

function whyRank(query: string, hit: ChannelHit, label: string) {
  if (isMeta(label)) return whyMeta(query, hit);
  const tokens = queryTokens(query);
  const inTitle = termsIn(hit.title, tokens);
  const inSnippet = termsIn(hit.snippet, tokens);
  const scope = label === "Google" ? "the open web" : label;
  const place = `Google placed this at organic position ${hit.rank} for “${query}” on ${scope}.`;
  const places = [
    inTitle.length ? `title (${inTitle.join(", ")})` : "",
    inSnippet.length ? `snippet (${inSnippet.join(", ")})` : "",
  ].filter(Boolean);
  if (places.length === 0) return `${place} The stored title and snippet do not repeat the search words, so the position is Google’s order only.`;
  return `${place} It stayed in this list because those words appear in the ${places.join(" and ")}.`;
}

function whyMeta(query: string, hit: ChannelHit) {
  const { matched, bait, specific } = metaScore(query, hit);
  const interest = matched.length ? wordList(matched) : "";
  if (bait) {
    return `Meta lowers ad quality for engagement bait. This creative matches ${interest || "little of the interest"}, but the quiz-style prompt asks for a reaction instead of describing the offer, so it ranks below a post that explains the program.`;
  }
  if (specific && interest) {
    return `Meta estimates the action rate from how closely the creative matches the interest, then weighs ad quality. This post matches ${interest} and names a concrete offer, which scores above a headline that only repeats the words.`;
  }
  if (interest) {
    return `Meta’s relevance signal is the overlap between the creative and the interest. This post matches ${interest} without stating what the person would get, so its ad quality is below a post that describes the offer.`;
  }
  return `Meta’s auction gives a low estimated action rate when the creative does not match “${query}”.`;
}

function matchFacts(query: string, hit: ChannelHit) {
  const tokens = queryTokens(query);
  const title = plainCreative(hit.title);
  const snippet = plainCreative(hit.snippet);
  const inTitle = termsIn(title, tokens);
  const inSnippet = termsIn(snippet, tokens);
  const matched = termsIn(`${title} ${snippet}`, tokens);
  const where = inTitle.length && inSnippet.length ? "Title and snippet" : inTitle.length ? "Title" : inSnippet.length ? "Snippet" : "None";
  return {
    matched: matched.join(", ") || "None",
    where,
    strength: `${matched.length} of ${tokens.length}`,
  };
}

function resultType(label: string, url: string) {
  const path = url.toLowerCase();
  if (label === "Instagram") {
    if (path.includes("/reel")) return "Reel";
    if (path.includes("/tv/")) return "Video";
    if (path.includes("/p/")) return "Post";
  }
  if (label === "Facebook") {
    if (path.includes("/reel")) return "Reel";
    if (path.includes("/posts") || path.includes("/videos")) return "Post";
  }
  if (label === "LinkedIn") {
    if (path.includes("/posts") || path.includes("/feed/update")) return "Post";
    if (path.includes("/pulse/")) return "Article";
  }
  return "Page";
}

function reasonColumns(query: string, hit: ChannelHit, label: string) {
  const facts = matchFacts(query, hit);
  if (!isMeta(label)) {
    return [
      { key: "position", header: "Google position", value: String(hit.rank) },
      { key: "type", header: "Result type", value: resultType(label, hit.url) },
      { key: "words", header: "Matched words", value: facts.matched },
      { key: "where", header: "Where matched", value: facts.where },
      { key: "strength", header: "Match strength", value: facts.strength },
    ];
  }
  const score = metaScore(query, hit);
  return [
    { key: "interest", header: "Interest match", value: facts.strength },
    { key: "offer", header: "Offer clarity", value: score.specific ? "Specific offer" : "Headline only" },
    { key: "quality", header: "Ad quality", value: score.bait ? "Lowered" : "Standard" },
    { key: "depth", header: "Creative depth", value: hit.snippet.trim().length >= 80 ? "Described" : "Thin" },
    { key: "words", header: "Matched words", value: facts.matched },
    { key: "where", header: "Where matched", value: facts.where },
  ];
}

function rankedHits(label: string, query: string, hits: ChannelHit[]) {
  if (!isMeta(label)) return hits.map((hit) => ({ hit, displayRank: hit.rank }));
  return [...hits]
    .sort((left, right) => metaScore(query, right).score - metaScore(query, left).score || left.rank - right.rank)
    .map((hit, index) => ({ hit, displayRank: index + 1 }));
}

export default function ChannelSearchPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [viewing, setViewing] = useState<HitView | null>(null);
  const closeDetails = useCallback(() => setViewing(null), []);
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
    refetchInterval: (query) => {
      const current = query.state.data;
      return Array.isArray(current) && current.some((row) => row.status === "running") ? 2000 : false;
    },
  });
  const search = useMutation({
    mutationFn: (query: string) => api<ChannelSearch>("/api/v1/channel-search", { method: "POST", body: JSON.stringify({ query }) }),
    onSuccess: (envelope) => {
      const created = envelope.data;
      if (created) setSelectedId(created.id);
      void client.invalidateQueries({ queryKey: ["channel-searches"] });
    },
    onError: () => {
      void client.invalidateQueries({ queryKey: ["channel-searches"] });
    },
  });

  if (!can("campaigns.read")) return <DeniedState />;
  if (status.isLoading || history.isLoading) return <LoadingState label="Reading channel search" />;
  if (status.isError || history.isError) return <ErrorState message="Channel search could not be loaded." />;

  const rows = history.data ?? [];
  const selected = rows.find((row) => row.id === selectedId) ?? rows[0];
  const searching = rows.some((row) => row.status === "running");
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
          <p className="mt-2 text-sm text-[var(--muted)]">
            {source.configured
              ? "Google and LinkedIn keep the public result position. Facebook and Instagram are ordered by interest relevance and ad quality, the creative signals in Meta’s ad auction."
              : source.detail}
          </p>
        </article>
      ) : null}
      {can("campaigns.write") ? (
        <form
          className="panel mb-6 flex flex-col gap-4 p-4 md:flex-row md:items-end"
          onSubmit={form.handleSubmit((values) => {
            if (searching) return;
            search.mutate(values.query);
          })}
        >
          <div className="min-w-0 flex-1">
            <Field label="Keyword or statement">
              <Input placeholder="Example: warehouse automation for mid-size distributors" {...form.register("query", { required: true, minLength: 2 })} />
            </Field>
          </div>
          <Button type="submit" disabled={search.isPending || searching}>
            {search.isPending || searching ? "Searching…" : "Search channels"}
          </Button>
        </form>
      ) : null}
      {search.isPending || searching ? <p className="mb-4 text-sm text-[var(--muted)]">Finished channels appear while the others are still searching. This usually takes about a minute.</p> : null}
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
          <div className="stack">
            {CHANNELS.map((channel) => {
              const bucket = selected.channels.find((item) => item.channel === channel.id);
              return (
                <ChannelTable
                  key={channel.id}
                  label={channel.label}
                  bucket={bucket}
                  query={selected.query}
                  searchedAt={selected.created_at}
                  onOpen={setViewing}
                />
              );
            })}
          </div>
        </div>
      ) : null}
      {viewing ? <HitDialog view={viewing} onClose={closeDetails} /> : null}
    </div>
  );
}

function ChannelTable({
  label,
  bucket,
  query,
  searchedAt,
  onOpen,
}: {
  label: string;
  bucket: ChannelBucket | undefined;
  query: string;
  searchedAt: string;
  onOpen: (view: HitView) => void;
}) {
  const hits = bucket?.hits ?? [];
  const sample = hits[0];
  const mode = bucket?.mode || "failed";
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{label}</h2>
        <Badge tone={mode === "live" ? "ok" : mode === "running" || mode === "not_configured" ? "gold" : "rose"}>
          {mode === "live" ? "Ranked" : mode === "running" ? "Searching" : mode === "not_configured" ? "Not configured" : "Unavailable"}
        </Badge>
      </header>
      {hits.length === 0 ? (
        <p className="panel-body text-sm text-[var(--muted)]">{bucket?.reason || "No public posts were returned for this keyword."}</p>
      ) : (
        <div className="table-wrap">
          <table className="rank-table">
            <thead>
              <tr>
                <th>Ranking</th>
                <th>Title</th>
                {sample
                  ? reasonColumns(query, sample, label).map((column) => (
                      <th key={column.key}>{column.header}</th>
                    ))
                  : null}
                <th>Why this rank</th>
              </tr>
            </thead>
            <tbody>
              {rankedHits(label, query, hits).map(({ hit, displayRank }) => {
                const view: HitView = {
                  label,
                  hit,
                  query,
                  provider: bucket?.provider || "",
                  mode,
                  searchedAt,
                  displayRank,
                };
                return (
                  <tr
                    key={`${hit.rank}-${hit.url}`}
                    className="result-row"
                    tabIndex={0}
                    onClick={() => onOpen(view)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onOpen(view);
                      }
                    }}
                  >
                    <td className="num">{displayRank}</td>
                    <td>{hit.title}</td>
                    {reasonColumns(query, hit, label).map((column) => (
                      <td key={column.key}>{column.value}</td>
                    ))}
                    <td>
                      <span className="connection-note">{whyRank(query, hit, label)}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function HitDialog({ view, onClose }: { view: HitView; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const parameter = rankingParameter(view.query, view.hit, view.label);
  const reason = whyRank(view.query, view.hit, view.label);
  const when = view.searchedAt ? new Date(view.searchedAt).toLocaleString() : "—";
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="hit-detail-title" data-testid="channel-hit-details">
      <button type="button" className="modal-scrim" aria-label="Close details" onClick={onClose} />
      <div className="modal-card" style={{ maxHeight: "min(760px, calc(100vh - 48px))", overflow: "auto" }}>
        <header className="modal-head">
          <h2 id="hit-detail-title">{view.hit.title}</h2>
          <Badge tone="gold">Rank {view.displayRank}</Badge>
        </header>
        <div className="modal-body">
          <Fact label="Channel" value={view.label} />
          <Fact label="Ranking" value={String(view.displayRank)} />
          <Fact label="Ranking parameter" value={parameter} />
          {reasonColumns(view.query, view.hit, view.label).map((column) => (
            <Fact key={column.key} label={column.header} value={column.value} />
          ))}
          <Fact label="Why this rank" value={reason} />
          <SnippetText snippet={view.hit.snippet} url={view.hit.url} />
          <Fact label="Search" value={view.query} />
          <Fact label="Provider" value={view.provider || "—"} />
          <Fact label="Result status" value={view.mode} />
          <Fact label="Searched" value={when} />
          <Fact label="Post address" value={view.hit.url} />
        </div>
        <footer className="modal-foot">
          <Button variant="line" onClick={onClose}>
            Close
          </Button>
          {view.hit.url ? (
            <a className="btn primary" href={view.hit.url} target="_blank" rel="noreferrer">
              Open post
            </a>
          ) : null}
        </footer>
      </div>
    </div>
  );
}

function snippetParts(snippet: string) {
  const match = snippet.match(/^(.*?)(?:\s*(?:\.{2,}|…)\s*)?read more\s*$/i);
  const preview = match?.[1]?.trim();
  if (preview === undefined) return { preview: snippet.trim(), expandable: false };
  return { preview, expandable: true };
}

function SnippetText({ snippet, url }: { snippet: string; url: string }) {
  const [detail, setDetail] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const parts = snippetParts(snippet);
  const open = async () => {
    setPending(true);
    setError("");
    try {
      const response = await api<{ text: string }>("/api/v1/channel-search/snippet", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      setDetail(response.data?.text || "");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The longer snippet could not be read.");
    } finally {
      setPending(false);
    }
  };
  return (
    <div>
      <p className="upper">Snippet</p>
      <p className="mt-1 whitespace-pre-wrap">
        {detail || parts.preview || "No snippet was stored."}
        {!detail && parts.expandable ? (
          <>
            {" "}
            <button type="button" className="text-link" onClick={() => void open()} disabled={pending}>
              {pending ? "Reading…" : "Read more"}
            </button>
          </>
        ) : null}
      </p>
      {error ? <p className="mt-2 text-sm text-[#e08b7a]">{error}</p> : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="upper">{label}</p>
      <p className="mt-1 whitespace-pre-wrap">{value}</p>
    </div>
  );
}
