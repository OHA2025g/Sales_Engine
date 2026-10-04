"use client";

import { Button, Input } from "@/components/ui";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

type TestMode = "chat" | "voice";
type Line = { role: "you" | "agent"; text: string };
type ChatTurn = {
  user_message?: { text?: string } | null;
  assistant_message?: { text?: string } | null;
};
type DograhTest = {
  ready: boolean;
  reason: string;
  voice_widget_src: string;
  chat_widget_src: string;
  sales_script: string;
};
type DograhWidgetApi = {
  start: () => void;
  end: () => void;
  startChat?: () => void;
  sendMessage?: (text: string) => Promise<ChatTurn[] | null>;
  setContext?: (vars: Record<string, string>) => void;
  onStatusChange?: (cb: (status: string, text?: string) => void) => void;
  onMessage?: (cb: (text: string) => void) => void;
  onChatStateChange?: (cb: (state: string) => void) => void;
  onError?: (cb: (err: Error) => void) => void;
};

declare global {
  interface Window {
    DograhWidget?: DograhWidgetApi;
  }
}

function widgetSrc(config: DograhTest, mode: TestMode): string {
  if (mode === "chat") return config.chat_widget_src;
  if (mode === "voice") return config.voice_widget_src;
  const unreachable: never = mode;
  return unreachable;
}

function turnsToLines(turns: ChatTurn[]): Line[] {
  const lines: Line[] = [];
  for (const turn of turns) {
    const user = turn.user_message?.text?.trim();
    const agent = turn.assistant_message?.text?.trim();
    if (user) lines.push({ role: "you", text: user });
    if (agent) lines.push({ role: "agent", text: agent });
  }
  return lines;
}

export function DograhTestPanel() {
  const query = useQuery({
    queryKey: ["dograh-browser-test"],
    queryFn: async () => (await api<DograhTest>("/api/v1/lifecycle/dograh/browser-test")).data,
  });
  const config = query.data;
  const [modeOverride, setModeOverride] = useState<TestMode | null>(null);
  const [scriptState, setScriptState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [voiceStatus, setVoiceStatus] = useState("idle");
  const [chatState, setChatState] = useState("idle");
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [sending, setSending] = useState(false);
  const mode: TestMode =
    modeOverride ?? (config?.voice_widget_src && !config.chat_widget_src ? "voice" : "chat");

  const activeSrc = config?.ready ? widgetSrc(config, mode) : "";

  useEffect(() => {
    if (!activeSrc) {
      setScriptState("idle");
      return;
    }
    let cancelled = false;
    setScriptState("loading");
    setError("");
    setLines([]);
    setVoiceStatus("idle");
    setChatState("idle");
    window.DograhWidget?.end?.();
    document.getElementById("dograh-widget")?.remove();
    const script = document.createElement("script");
    script.id = "dograh-widget";
    script.async = true;
    script.src = activeSrc;
    script.onload = () => {
      if (!cancelled) setScriptState("ready");
    };
    script.onerror = () => {
      if (cancelled) return;
      setScriptState("error");
      setError("The Dograh widget did not load. This browser must be able to reach the Dograh website, over HTTPS when this site is HTTPS.");
    };
    document.body.appendChild(script);
    return () => {
      cancelled = true;
      window.DograhWidget?.end?.();
      script.remove();
    };
  }, [activeSrc]);

  useEffect(() => {
    if (scriptState !== "ready" || !window.DograhWidget) return;
    const widget = window.DograhWidget;
    widget.onError?.((err) => setError(err.message || "Dograh could not start the test."));
    widget.onStatusChange?.((status, text) => {
      setVoiceStatus(status);
      if (text) setStatusText(text);
    });
    widget.onChatStateChange?.((state) => setChatState(state));
    widget.onMessage?.((text) => {
      const reply = text.trim();
      if (!reply) return;
      setLines((prev) =>
        prev.some((line) => line.role === "agent" && line.text === reply) ? prev : [...prev, { role: "agent", text: reply }],
      );
    });
  }, [scriptState, activeSrc]);

  function applyContext() {
    const script = config?.sales_script?.trim();
    if (script) window.DograhWidget?.setContext?.({ sales_script: script });
  }

  function onStart() {
    const widget = window.DograhWidget;
    if (!widget || scriptState !== "ready") return;
    setError("");
    applyContext();
    if (mode === "voice") {
      if (voiceStatus === "connected" || voiceStatus === "connecting") {
        widget.end();
        return;
      }
      widget.start();
      return;
    }
    if (mode === "chat") {
      if (widget.startChat) widget.startChat();
      else widget.start();
      return;
    }
    const unreachable: never = mode;
    return unreachable;
  }

  async function onSend() {
    const text = draft.trim();
    const widget = window.DograhWidget;
    if (!text || !widget?.sendMessage || sending) return;
    setSending(true);
    setDraft("");
    setLines((prev) => [...prev, { role: "you", text }]);
    try {
      const turns = await widget.sendMessage(text);
      if (turns) setLines(turnsToLines(turns));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dograh did not accept that message.");
    } finally {
      setSending(false);
    }
  }

  if (query.isLoading) {
    return <section className="panel mb-6 p-4 text-sm text-[var(--muted)]">Checking the Dograh browser test.</section>;
  }
  if (query.isError || !config) {
    return <section className="panel mb-6 p-4 text-sm">The Dograh test status could not be loaded.</section>;
  }

  const chatOpen = mode === "chat" && (chatState === "ready" || chatState === "waiting" || chatState === "starting");
  const voiceLabel =
    voiceStatus === "connecting" ? "Connecting" : voiceStatus === "connected" ? "End audio test" : voiceStatus === "failed" ? "Retry audio test" : "Start audio test";

  return (
    <section className="panel mb-6 space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-navy">Test agent</p>
          <p className="text-sm text-[var(--muted)]">Ask the Dograh agent here. This does not dial a phone.</p>
        </div>
        {config.chat_widget_src && config.voice_widget_src ? (
          <div className="flex gap-2">
            <Button variant={mode === "chat" ? "primary" : "line"} onClick={() => setModeOverride("chat")}>Chat</Button>
            <Button variant={mode === "voice" ? "primary" : "line"} onClick={() => setModeOverride("voice")}>Audio</Button>
          </div>
        ) : null}
      </div>

      {!config.ready ? (
        <div className="space-y-2 text-sm">
          <p>{config.reason}</p>
          <ol className="list-decimal space-y-1 pl-5 text-[var(--muted)]">
            <li>In Dograh, open the agent settings and choose Configure Widget.</li>
            <li>Turn embedding on. Pick Chat or Voice, and set the embed mode to Headless.</li>
            <li>Add this website’s address to Allowed Domains, or leave that list empty.</li>
            <li>Copy the token from the widget script into DOGRAH_CHAT_EMBED_TOKEN or DOGRAH_EMBED_TOKEN, then restart the API.</li>
            <li>If the Dograh website and API are different hosts, set DOGRAH_UI_BASE to the website address.</li>
          </ol>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-[var(--muted)]">
            {scriptState === "loading" ? "Loading the Dograh widget." : statusText || (mode === "voice" ? voiceStatus : chatState)}
          </p>
          {error ? <p className="text-sm text-red-700">{error}</p> : null}
          {!activeSrc ? <p className="text-sm">This mode needs its own embed token.</p> : null}
          <Button onClick={onStart} disabled={scriptState !== "ready" || chatOpen}>
            {mode === "chat" ? (chatOpen ? "Chat is open" : "Start chat") : voiceLabel}
          </Button>
          {mode === "chat" && lines.length > 0 ? (
            <div className="max-h-80 space-y-2 overflow-y-auto rounded-lg border border-[var(--line)] bg-[#101722] p-3">
              {lines.map((line, index) => (
                <p key={`${line.role}-${index}`} className="text-sm">
                  <span className="font-semibold text-navy">{line.role === "agent" ? "Agent" : "You"}: </span>
                  {line.text}
                </p>
              ))}
            </div>
          ) : null}
          {mode === "chat" && chatOpen ? (
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                void onSend();
              }}
            >
              <Input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about the knowledge base" />
              <Button type="submit" disabled={sending || chatState === "waiting" || !draft.trim()}>Send</Button>
            </form>
          ) : null}
        </div>
      )}
    </section>
  );
}
