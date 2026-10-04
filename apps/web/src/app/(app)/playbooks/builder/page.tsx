"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState } from "@/components/states";
import { Button, Field, Input, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function PlaybookBuilderPage() {
  const { can } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [trigger, setTrigger] = useState("lead.created");
  const [action, setAction] = useState("create_task");
  const [notice, setNotice] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api("/api/v1/lifecycle/playbooks", {
        method: "POST",
        body: JSON.stringify({
          name,
          trigger_event: trigger,
          autonomy_level: 1,
          actions_json: JSON.stringify([{ type: action, title: name }]),
          is_active: false,
        }),
      }),
    onSuccess: () => router.push("/playbooks"),
    onError: (error: Error) => setNotice(error.message),
  });
  if (!can("revops.read")) return <DeniedState />;
  return (
    <div>
      <PageHeader
        eyebrow="Autopilot"
        title="Playbook builder"
        subtitle="Supported actions are create a task, write an activity, or request approval. The playbook stays inactive until it is turned on."
        nextHref="/policies"
        nextLabel="Policies"
      />
      <form
        className="panel max-w-xl space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          if (!can("revops.write")) {
            setNotice("Saving a playbook needs revops.write.");
            return;
          }
          save.mutate();
        }}
      >
        <Field label="Name"><Input value={name} onChange={(event) => setName(event.target.value)} required /></Field>
        <Field label="Trigger"><Input value={trigger} onChange={(event) => setTrigger(event.target.value)} /></Field>
        <Field label="Action">
          <Select value={action} onChange={(event) => setAction(event.target.value)}>
            <option value="create_task">Create task</option>
            <option value="write_activity">Write activity</option>
            <option value="request_approval">Request approval</option>
          </Select>
        </Field>
        <Button type="submit" disabled={save.isPending}>Save inactive playbook</Button>
        {notice ? <p className="text-sm text-[var(--rose)]">{notice}</p> : null}
      </form>
    </div>
  );
}
