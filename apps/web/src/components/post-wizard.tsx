"use client";

import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { ApiError, api } from "@agrayian/sdk";
import Link from "next/link";
import { useState } from "react";

export type WizardForm = { id: string; name: string; status: string; url: string };

export type WizardSource = {
  id: string;
  channel: string;
  status: string;
  body: string;
  headline: string;
  keyword: string;
  ranking_parameter: string;
  snippet: string;
  context: string;
  image_url: string;
  video_url: string;
  form_key_id: string | null;
};

type Step = 1 | 2 | 3 | 4 | 5 | 6;

const STEPS: { id: Exclude<Step, 6>; label: string }[] = [
  { id: 1, label: "Brief" },
  { id: 2, label: "Post" },
  { id: 3, label: "Banner and video" },
  { id: 4, label: "Preview" },
  { id: 5, label: "Channels" },
];

const CHANNELS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "facebook", label: "Facebook" },
  { id: "instagram", label: "Instagram" },
  { id: "youtube", label: "YouTube" },
] as const;

type Brief = {
  headline: string;
  keyword: string;
  ranking_parameter: string;
  snippet: string;
  context: string;
  body: string;
  image_url: string;
  image_note: string;
  video_url: string;
  video_note: string;
  video_kind: string;
  form_key_id: string;
  channels: string[];
};

function briefFromSource(source: WizardSource): Brief {
  const storedHeadline = source.headline.trim();
  const firstLine = source.body.split("\n")[0]?.trim() || "";
  const headline = storedHeadline || firstLine;
  const descriptive = source.body.startsWith(headline) ? source.body.slice(headline.length).trim() : source.body.trim();
  const channel = CHANNELS.some((item) => item.id === source.channel) ? [source.channel] : [];
  return {
    headline,
    keyword: source.keyword,
    ranking_parameter: source.ranking_parameter,
    snippet: source.snippet,
    context: source.context || headline,
    body: descriptive || source.body.trim(),
    image_url: source.image_url,
    image_note: "",
    video_url: source.video_url,
    video_note: "",
    video_kind: source.video_url ? "video" : "",
    form_key_id: source.form_key_id || "",
    channels: channel,
  };
}

function blank(): Brief {
  return {
    headline: "",
    keyword: "",
    ranking_parameter: "",
    snippet: "",
    context: "",
    body: "",
    image_url: "",
    image_note: "",
    video_url: "",
    video_note: "",
    video_kind: "",
    form_key_id: "",
    channels: [],
  };
}

function messageOf(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export function PostWizard({
  forms,
  source,
  onClose,
  onSaved,
}: {
  forms: WizardForm[];
  source?: WizardSource | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [step, setStep] = useState<Step>(1);
  const [brief, setBrief] = useState<Brief>(source ? briefFromSource(source) : blank);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  function patch(next: Partial<Brief>) {
    setBrief((current) => ({ ...current, ...next }));
  }

  function ready(target: Step) {
    if (target === 1) return "";
    if (!brief.headline.trim()) return "Add a headline.";
    if (!brief.keyword.trim() || !brief.ranking_parameter.trim() || !brief.snippet.trim()) {
      return "Add the keyword, the ranking parameter, and the snippet.";
    }
    if (!brief.context.trim()) return "Add a one-line context.";
    if (target === 2) return "";
    if (!brief.body.trim()) return "Generate the post or paste one.";
    if (target <= 5) return "";
    if (brief.channels.length === 0) return "Choose where this post will go live.";
    return "";
  }

  function go(target: Step) {
    const problem = ready(target);
    setError(problem);
    if (!problem) setStep(target);
  }

  async function generate() {
    const problem = ready(2);
    setError(problem);
    if (problem) return;
    setBusy("Writing the post…");
    try {
      const written = await api<{ body: string }>("/api/v1/social/compose", {
        method: "POST",
        body: JSON.stringify({
          headline: brief.headline,
          keyword: brief.keyword,
          ranking_parameter: brief.ranking_parameter,
          snippet: brief.snippet,
          context: brief.context,
        }),
      });
      if (written.data?.body) patch({ body: written.data.body });
    } catch (caught) {
      setError(messageOf(caught, "The post was not written."));
    } finally {
      setBusy("");
    }
  }

  async function creative(kind: "banner" | "video") {
    const problem = ready(3);
    setError(problem);
    if (problem) return;
    setBusy(kind === "banner" ? "Creating the banner…" : "Creating the short video…");
    try {
      const saved = await api<{ url: string; note: string; kind: string }>(`/api/v1/social/${kind}`, {
        method: "POST",
        body: JSON.stringify({
          headline: brief.headline,
          keyword: brief.keyword,
          ranking_parameter: brief.ranking_parameter,
          snippet: brief.snippet,
          context: brief.context,
          body: brief.body,
        }),
      });
      if (saved.data?.url) {
        patch(
          kind === "banner"
            ? { image_url: saved.data.url, image_note: saved.data.note || "" }
            : { video_url: saved.data.url, video_note: saved.data.note || "", video_kind: saved.data.kind || "video" },
        );
      }
    } catch (caught) {
      setError(messageOf(caught, kind === "banner" ? "The banner was not created." : "The short video was not created."));
    } finally {
      setBusy("");
    }
  }

  async function save() {
    const problem = ready(6);
    setError(problem);
    if (problem) return;
    setBusy("Saving…");
    try {
      await api(source ? `/api/v1/social/posts/${source.id}/revision` : "/api/v1/social/submissions", {
        method: "POST",
        body: JSON.stringify({
          headline: brief.headline,
          keyword: brief.keyword,
          ranking_parameter: brief.ranking_parameter,
          snippet: brief.snippet,
          context: brief.context,
          body: brief.body,
          image_url: brief.image_url,
          video_url: brief.video_url,
          form_key_id: brief.form_key_id || null,
          channels: brief.channels,
        }),
      });
      onSaved();
      setStep(6);
    } catch (caught) {
      setError(messageOf(caught, "The post could not be saved."));
    } finally {
      setBusy("");
    }
  }

  const formName = forms.find((row) => row.id === brief.form_key_id)?.name || "";
  const activeForms = forms.filter((row) => row.status === "active" && row.url);

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="post-wizard-title">
      <button type="button" className="modal-scrim" aria-label={source ? "Close edit post" : "Close new post"} onClick={onClose} />
      <div className="modal-card post-wizard">
        <div className="modal-head">
          <h2 id="post-wizard-title">{source ? "Edit post" : "New post"}</h2>
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
        <div
          className="post-wizard-steps"
          role="tablist"
          aria-label="Post steps"
          onKeyDown={(event) => {
            const current = STEPS.findIndex((item) => item.id === step);
            if (current < 0) return;
            const next =
              event.key === "ArrowRight" || event.key === "ArrowDown"
                ? (current + 1) % STEPS.length
                : event.key === "ArrowLeft" || event.key === "ArrowUp"
                  ? (current - 1 + STEPS.length) % STEPS.length
                  : event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? STEPS.length - 1
                      : -1;
            const target = next < 0 ? undefined : STEPS[next];
            if (!target) return;
            event.preventDefault();
            go(target.id);
          }}
        >
          {STEPS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`post-step-${item.id}`}
              aria-selected={step === item.id}
              aria-controls="post-wizard-panel"
              tabIndex={step === item.id ? 0 : -1}
              onClick={() => go(item.id)}
            >
              <span>{item.id}</span>
              {item.label}
            </button>
          ))}
        </div>
        <div
          className="modal-body"
          role="tabpanel"
          id="post-wizard-panel"
          aria-labelledby={step < 6 ? `post-step-${step}` : undefined}
        >
          {step === 6 ? (
            <div className="stack">
              <p>
                {source?.status === "published"
                  ? "Saved. This update is in the approvers list. The post already live stays as it is until this update is approved."
                  : "Saved. This post is in the approvers list. It is not posted until someone approves it."}
              </p>
              <Link href="/automation/approvals" className="text-brand">
                Open approvers list
              </Link>
            </div>
          ) : (
            <StepFields
              step={step}
              brief={brief}
              formName={formName}
              forms={activeForms}
              busy={busy}
              onChange={patch}
              onGenerate={() => void generate()}
              onBanner={() => void creative("banner")}
              onVideo={() => void creative("video")}
            />
          )}
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
          {busy ? <p className="text-sm text-[var(--muted)]">{busy}</p> : null}
        </div>
        <div className="modal-foot">
          {step > 1 && step < 6 ? (
            <Button type="button" variant="line" onClick={() => setStep((current) => (current > 1 ? ((current - 1) as Step) : current))}>
              Back
            </Button>
          ) : null}
          {step < 5 ? (
            <Button type="button" onClick={() => go((step + 1) as Step)}>
              Continue
            </Button>
          ) : null}
          {step === 5 ? (
            <Button type="button" disabled={Boolean(busy)} onClick={() => void save()}>
              Save
            </Button>
          ) : null}
          {step === 6 ? (
            <Button type="button" onClick={onClose}>
              Done
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Clip({ url, kind }: { url: string; kind: string }) {
  if (kind === "image") return <img className="post-wizard-banner" src={url} alt="Short clip" />;
  return <video className="post-wizard-banner" src={url} controls />;
}

function StepFields({
  step,
  brief,
  formName,
  forms,
  busy,
  onChange,
  onGenerate,
  onBanner,
  onVideo,
}: {
  step: Exclude<Step, 6>;
  brief: Brief;
  formName: string;
  forms: WizardForm[];
  busy: string;
  onChange: (next: Partial<Brief>) => void;
  onGenerate: () => void;
  onBanner: () => void;
  onVideo: () => void;
}) {
  switch (step) {
    case 1:
      return (
        <div className="post-wizard-sections">
          <section className="post-wizard-section">
            <h3>Title</h3>
            <Field label="Headline / title">
              <Input value={brief.headline} onChange={(event) => onChange({ headline: event.target.value })} />
            </Field>
          </section>
          <section className="post-wizard-section">
            <h3>Ranking</h3>
            <Field label="Keyword">
              <Input value={brief.keyword} onChange={(event) => onChange({ keyword: event.target.value })} />
            </Field>
            <Field label="Parameter the ranking is based on">
              <Input value={brief.ranking_parameter} onChange={(event) => onChange({ ranking_parameter: event.target.value })} />
            </Field>
            <Field label="Snippet details">
              <Textarea rows={4} value={brief.snippet} onChange={(event) => onChange({ snippet: event.target.value })} />
            </Field>
          </section>
          <section className="post-wizard-section">
            <h3>Context</h3>
            <Field label="Context">
              <Input
                value={brief.context}
                placeholder="One line about this post"
                onChange={(event) => onChange({ context: event.target.value })}
              />
            </Field>
          </section>
        </div>
      );
    case 2:
      return (
        <div className="post-wizard-sections">
          <section className="post-wizard-section">
            <h3>Post</h3>
            <div className="ds-flex">
              <Button type="button" disabled={Boolean(busy)} onClick={onGenerate}>
                Generate detailed post
              </Button>
              <p className="text-sm text-[var(--muted)]">Or paste a post you already wrote.</p>
            </div>
            <Field label="Descriptive post">
              <Textarea rows={8} value={brief.body} onChange={(event) => onChange({ body: event.target.value })} />
            </Field>
          </section>
          <section className="post-wizard-section">
            <h3>Form</h3>
            <Field label="Form">
              <Select value={brief.form_key_id} onChange={(event) => onChange({ form_key_id: event.target.value })}>
                <option value="">No form</option>
                {forms.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </Select>
            </Field>
            <p className="text-sm text-[var(--muted)]">
              {formName
                ? `A click on the post link or banner opens ${formName}.`
                : "Choose a form if a click on the link or banner should open one."}
            </p>
          </section>
        </div>
      );
    case 3:
      return (
        <div className="stack">
          <p className="text-sm text-[var(--muted)]">
            The banner and video use the title, context, and descriptive post. The keyword, ranking parameter, and snippet guide the picture and stay off the banner.
          </p>
          <div className="ds-flex">
            <Button type="button" disabled={Boolean(busy)} onClick={onBanner}>
              Create banner
            </Button>
            <Button type="button" variant="line" disabled={Boolean(busy)} onClick={onVideo}>
              Create short video
            </Button>
          </div>
          {brief.image_url ? <img className="post-wizard-banner" src={brief.image_url} alt="Banner" /> : null}
          {brief.image_note ? <p className="text-sm text-[var(--muted)]">{brief.image_note}</p> : null}
          {brief.video_url ? <Clip url={brief.video_url} kind={brief.video_kind} /> : null}
          {brief.video_note ? <p className="text-sm text-[var(--muted)]">{brief.video_note}</p> : null}
        </div>
      );
    case 4:
      return (
        <article className="channel-preview">
          <p className="text-sm font-medium text-navy">{brief.headline}</p>
          {brief.image_url ? <img className="post-wizard-banner" src={brief.image_url} alt="" /> : <p className="text-sm text-[var(--muted)]">No banner yet.</p>}
          {brief.video_url ? <Clip url={brief.video_url} kind={brief.video_kind} /> : null}
          <p className="whitespace-pre-wrap text-sm">{brief.body}</p>
          {formName ? <p className="text-sm text-[var(--muted)]">Opens {formName}</p> : null}
        </article>
      );
    case 5:
      return (
        <div className="stack">
          <p className="text-sm text-[var(--muted)]">Choose where this post will go live after it is approved.</p>
          {CHANNELS.map((channel) => (
            <label key={channel.id} className="ds-flex">
              <input
                type="checkbox"
                checked={brief.channels.includes(channel.id)}
                onChange={(event) =>
                  onChange({
                    channels: event.target.checked
                      ? [...brief.channels, channel.id]
                      : brief.channels.filter((item) => item !== channel.id),
                  })
                }
              />
              {channel.label}
            </label>
          ))}
          {brief.channels.includes("instagram") && !brief.image_url ? (
            <p className="text-sm text-[var(--muted)]">Instagram needs a banner before it can be posted.</p>
          ) : null}
          {brief.channels.includes("youtube") && !brief.video_url ? (
            <p className="text-sm text-[var(--muted)]">YouTube needs the short video before it can be posted.</p>
          ) : null}
        </div>
      );
    default: {
      const uncovered: never = step;
      return uncovered;
    }
  }
}
