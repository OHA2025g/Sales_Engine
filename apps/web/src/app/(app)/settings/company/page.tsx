"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { Button, Field, Input, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

type Profile = {
  company_name: string;
  summary: string;
  audience: string;
  website: string;
  proof: string;
  capture_url: string;
};

export default function CompanyPage() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [form, setForm] = useState<Profile>({ company_name: "", summary: "", audience: "", website: "", proof: "", capture_url: "" });
  const [notice, setNotice] = useState("");
  const query = useQuery({
    queryKey: ["content-profile"],
    queryFn: async () => (await api<Profile>("/api/v1/content/profile")).data,
    enabled: can("campaigns.read"),
  });
  useEffect(() => {
    if (query.data) setForm(query.data);
  }, [query.data]);
  const save = useMutation({
    mutationFn: () => api("/api/v1/content/profile", { method: "PUT", body: JSON.stringify(form) }),
    onSuccess: () => {
      setNotice("Company profile saved.");
      void client.invalidateQueries({ queryKey: ["content-profile"] });
    },
    onError: (error: Error) => setNotice(error.message),
  });
  if (!can("campaigns.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading the company" />;
  if (query.isError) return <ErrorState message="The company profile could not be loaded." />;
  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="Company"
        subtitle="This is the offer the content studio and launch use. It is not a fictional portfolio."
        nextHref="/setup"
        nextLabel="Launch"
      />
      <form
        className="panel max-w-2xl space-y-4 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Company"><Input value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} /></Field>
        <Field label="Offer"><Textarea rows={4} value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} /></Field>
        <Field label="Audience"><Input value={form.audience} onChange={(event) => setForm({ ...form, audience: event.target.value })} /></Field>
        <Field label="Website"><Input value={form.website} onChange={(event) => setForm({ ...form, website: event.target.value })} /></Field>
        <Field label="Proof"><Textarea rows={3} value={form.proof} onChange={(event) => setForm({ ...form, proof: event.target.value })} /></Field>
        {can("campaigns.write") ? <Button type="submit" disabled={save.isPending}>Save</Button> : null}
        {notice ? <p className="text-sm text-[var(--muted)]">{notice}</p> : null}
      </form>
    </div>
  );
}
