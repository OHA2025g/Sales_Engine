"use client";

import { Notice, Panel, Stats } from "@/components/ds";
import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

type SignalRow = {
  code: string;
  label: string;
  description: string;
  category: string;
  cost_note: string;
  collectable: boolean;
  status: string;
  accounts: number;
};

type Board = {
  signals: SignalRow[];
  recent: { id: string; account_name: string; label: string; opening: string; evidence_url: string }[];
  last_run: { accounts_read: number; observations: number; skipped: number; note: string } | null;
};

type Cohort = {
  count: number;
  accounts: { account_id: string; name: string; website: string; opening: string }[];
};

const CATEGORIES = [
  ["discovery", "Discovery"],
  ["profile", "Public site"],
  ["people", "People"],
  ["verification", "Reachability"],
] as const;

function statusTone(status: string): "neutral" | "gold" | "mint" | "rose" {
  if (status === "confirmed") return "mint";
  if (status === "rejected") return "rose";
  if (status === "skipped") return "neutral";
  return "gold";
}

function titleCase(value: string) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
}

export default function SiteSignalsPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [requireCodes, setRequireCodes] = useState<string[]>([]);
  const [excludeCodes, setExcludeCodes] = useState<string[]>([]);
  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [notice, setNotice] = useState("");
  const allowed = can("signals.read");
  const board = useQuery({
    queryKey: ["site-signals"],
    queryFn: async () => (await api<Board>("/api/v1/site-signals")).data,
    enabled: allowed,
  });
  const decide = useMutation({
    mutationFn: (body: { codes: string[]; status: string }) =>
      api<Board>("/api/v1/site-signals/status", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setNotice("");
      void client.invalidateQueries({ queryKey: ["site-signals"] });
    },
  });
  const profile = useMutation({
    mutationFn: () =>
      api<{ note: string; accounts_read: number; observations: number }>("/api/v1/site-signals/profile", {
        method: "POST",
        body: JSON.stringify({ limit: 10 }),
      }),
    onSuccess: (result) => {
      const data = result.data;
      setNotice(data?.note || `Read ${data?.accounts_read ?? 0} accounts and stored ${data?.observations ?? 0} observations.`);
      void client.invalidateQueries({ queryKey: ["site-signals"] });
    },
  });
  const count = useMutation({
    mutationFn: () =>
      api<Cohort>("/api/v1/site-signals/cohort", {
        method: "POST",
        body: JSON.stringify({ require: requireCodes, exclude: excludeCodes }),
      }),
    onSuccess: (result) => setCohort(result.data ?? { count: 0, accounts: [] }),
  });

  if (!allowed) return <DeniedState />;
  if (board.isLoading) return <LoadingState label="Loading website signals" />;
  if (board.isError || !board.data) return <ErrorState message="Website signals could not be loaded." />;

  const signals = board.data.signals;
  const free = signals.filter((signal) => signal.collectable).map((signal) => signal.code);
  const confirmed = signals.filter((signal) => signal.status === "confirmed").length;
  const proposed = signals.filter((signal) => signal.status === "proposed").length;
  const grouped: { id: string; label: string; signals: SignalRow[] }[] = CATEGORIES.map(([id, label]) => ({
    id,
    label,
    signals: signals.filter((signal) => signal.category === id),
  })).filter((group) => group.signals.length > 0);
  const leftover = signals.filter((signal) => !CATEGORIES.some(([id]) => id === signal.category));
  if (leftover.length) grouped.push({ id: "other", label: "Other", signals: leftover });
  const toggle = (list: string[], code: string, setList: (next: string[]) => void) => {
    setList(list.includes(code) ? list.filter((item) => item !== code) : [...list, code]);
  };
  const last = board.data.last_run;

  return (
    <div>
      <PageHeader
        title="Website signals"
        subtitle="Confirm the facts worth collecting. The reader uses public pages only, costs nothing, and does not send email."
        actions={
          can("signals.write") ? (
            <>
              <Button variant="line" disabled={decide.isPending} onClick={() => decide.mutate({ codes: free, status: "confirmed" })}>
                Confirm free signals
              </Button>
              <Button disabled={profile.isPending} onClick={() => profile.mutate()}>
                Read account websites
              </Button>
            </>
          ) : null
        }
      />
      <Stats
        items={[
          { name: "Confirmed", value: String(confirmed), note: "Ready for the reader" },
          { name: "Still proposed", value: String(proposed), note: "Waiting for a decision" },
          { name: "Free to read", value: String(free.length), note: "Public pages only" },
          {
            name: "Last read",
            value: last ? String(last.accounts_read) : "—",
            note: last ? `${last.observations} observations stored` : "No website read yet",
          },
        ]}
      />
      {notice ? <Notice title="Website read finished" body={notice} kind="good" /> : null}
      {profile.isError ? <ErrorState message="The website read could not finish." /> : null}
      <Panel title="Catalog" extra={<span className="small muted">Paid signals stay listed and are not collected</span>}>
        <div className="signal-groups">
          {grouped.map((group) => (
            <section key={group.id}>
              <h3 className="upper">{group.label}</h3>
              <div className="signal-grid">
                {group.signals.map((signal) => (
                  <article key={signal.code} className="signal-card">
                    <div className="signal-card-top">
                      <h3>{signal.label}</h3>
                      <Badge tone={statusTone(signal.status)}>{titleCase(signal.status)}</Badge>
                    </div>
                    <p className="small">{signal.description}</p>
                    <p className="small muted">{signal.cost_note}</p>
                    <p className="small muted">{signal.accounts} accounts</p>
                    {can("signals.write") ? (
                      <div className="signal-card-actions">
                        <Button variant="line" onClick={() => decide.mutate({ codes: [signal.code], status: "confirmed" })}>
                          Confirm
                        </Button>
                        <Button variant="ghost" onClick={() => decide.mutate({ codes: [signal.code], status: "skipped" })}>
                          Skip
                        </Button>
                        <Button variant="ghost" onClick={() => decide.mutate({ codes: [signal.code], status: "rejected" })}>
                          Reject
                        </Button>
                      </div>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </Panel>
      <div className="ds-grid wide" style={{ marginTop: 20 }}>
        <Panel title="Cohort" extra={<span className="small muted">The first line is the fact</span>}>
          <p className="small muted">Must-have signals are facts that are true. Excluded signals remove an account.</p>
          <div className="cohort-table">
            <div className="cohort-row cohort-head">
              <span>Signal</span>
              <span>Must have</span>
              <span>Exclude</span>
            </div>
            {signals
              .filter((signal) => signal.collectable)
              .map((signal) => (
                <div className="cohort-row" key={signal.code}>
                  <span className="cohort-name">{signal.label}</span>
                  <label>
                    <input
                      type="checkbox"
                      checked={requireCodes.includes(signal.code)}
                      onChange={() => toggle(requireCodes, signal.code, setRequireCodes)}
                    />
                    Must have
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={excludeCodes.includes(signal.code)}
                      onChange={() => toggle(excludeCodes, signal.code, setExcludeCodes)}
                    />
                    Exclude
                  </label>
                </div>
              ))}
          </div>
          <div className="signal-card-actions">
            <Button
              disabled={count.isPending || (requireCodes.length === 0 && excludeCodes.length === 0)}
              onClick={() => count.mutate()}
            >
              Count matches
            </Button>
          </div>
          {count.isError ? <ErrorState message="The cohort could not be counted." /> : null}
          {cohort ? (
            <div className="signal-groups" style={{ marginTop: 16 }}>
              <p>
                <strong className="num">{cohort.count}</strong> accounts
              </p>
              {cohort.accounts.length === 0 ? <p className="small muted">No account currently matches.</p> : null}
              {cohort.accounts.map((account) => (
                <article key={account.account_id} className="signal-card">
                  <h3>
                    <Link href={`/accounts/${account.account_id}`}>{account.name}</Link>
                  </h3>
                  <p>{account.opening}</p>
                  {account.website ? <p className="small muted">{account.website}</p> : null}
                </article>
              ))}
            </div>
          ) : null}
        </Panel>
        <Panel title="Recent observations">
          {board.data.recent.length === 0 ? <p className="small muted">No website has been read yet.</p> : null}
          {board.data.recent.map((item) => (
            <article key={item.id} className="signal-card" style={{ marginBottom: 10 }}>
              <h3>{item.account_name || "Account"}</h3>
              <p className="small">{item.label}</p>
              {item.opening ? <p>{item.opening}</p> : null}
              {item.evidence_url ? (
                <p className="small muted">
                  <a href={item.evidence_url}>{item.evidence_url}</a>
                </p>
              ) : null}
            </article>
          ))}
          {last ? (
            <p className="small muted">
              Last read: {last.accounts_read} accounts, {last.observations} observations, {last.skipped} skipped.
              {last.note ? ` ${last.note}` : ""}
            </p>
          ) : null}
        </Panel>
      </div>
    </div>
  );
}
