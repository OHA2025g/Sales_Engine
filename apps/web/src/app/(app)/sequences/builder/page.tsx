"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState } from "@/components/states";
import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SequenceBuilderPage() {
  const { can } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("email");
  const [template, setTemplate] = useState("");
  const [notice, setNotice] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api<{ id: string }>("/api/v1/lifecycle/sequences", {
        method: "POST",
        body: JSON.stringify({
          name,
          channel,
          status: "draft",
          purpose: "sdr",
          steps: [{ position: 1, delay_days: 0, action_type: "email_draft", template }],
        }),
      }),
    onSuccess: (result) => {
      const id = result.data?.id;
      if (id) router.push(`/sequences/${id}`);
    },
    onError: (error: Error) => setNotice(error.message),
  });
  if (!can("sequences.write")) return <DeniedState />;
  return (
    <div>
      <PageHeader
        eyebrow="Sales"
        title="Sequence builder"
        subtitle="This saves a draft. Activation is a separate decision, and a send still needs a bounded grant."
        nextHref="/sequences"
        nextLabel="Sequences"
      />
      <form
        className="panel max-w-2xl space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Name"><Input value={name} onChange={(event) => setName(event.target.value)} required /></Field>
        <Field label="Channel">
          <Select value={channel} onChange={(event) => setChannel(event.target.value)}>
            <option value="email">Email</option>
            <option value="linkedin">LinkedIn</option>
          </Select>
        </Field>
        <Field label="First step">
          <Textarea rows={6} value={template} onChange={(event) => setTemplate(event.target.value)} placeholder="Draft the first email. It is not sent from this screen." />
        </Field>
        <Button type="submit" disabled={save.isPending}>Save draft</Button>
        {notice ? <p className="text-sm text-[var(--rose)]">{notice}</p> : null}
      </form>
    </div>
  );
}
