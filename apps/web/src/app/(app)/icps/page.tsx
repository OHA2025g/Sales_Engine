"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge, Button, CheckField, Drawer, Field, FormActions, Input, Textarea } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import type { ICP } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";

type ICPForm = {
  name: string;
  industries: string;
  geographies: string;
  min_employees: number | null;
  max_employees: number | null;
  description: string;
  is_default: boolean;
  personas: string;
  seniorities: string;
  job_functions: string;
  target_companies: string;
  keywords: string;
};

const EMPTY_FORM: ICPForm = {
  name: "",
  industries: "",
  geographies: "",
  min_employees: null,
  max_employees: null,
  description: "",
  is_default: false,
  personas: "",
  seniorities: "",
  job_functions: "",
  target_companies: "",
  keywords: "",
};

const EDITOR_ROLES = new Set(["admin", "tenant admin", "super admin"]);

function splitList(value: string | undefined): string[] {
  return (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function shown(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function toForm(row: ICP): ICPForm {
  return {
    name: row.name,
    industries: row.industries || "",
    geographies: row.geographies || "",
    min_employees: row.min_employees,
    max_employees: row.max_employees ?? null,
    description: row.description || "",
    is_default: row.is_default,
    personas: row.personas || "",
    seniorities: row.seniorities || "",
    job_functions: row.job_functions || "",
    target_companies: row.target_companies || "",
    keywords: row.keywords || "",
  };
}

function toPayload(body: ICPForm) {
  const count = (value: number | null) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return null;
    const parsed = Number(value);
    return parsed > 0 ? parsed : null;
  };
  return {
    ...body,
    min_employees: count(body.min_employees),
    max_employees: count(body.max_employees),
  };
}

function ChipRow({ label, values }: { label: string; values: string[] }) {
  const visible = values.slice(0, 4);
  const extra = values.length - visible.length;
  return (
    <div>
      <p className="text-xs text-[var(--muted)]">{label}</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {visible.map((item) => (
          <Badge key={item} tone={label === "Industries" ? "blue" : "neutral"}>
            {item}
          </Badge>
        ))}
        {extra > 0 ? <Badge tone="neutral">+{extra}</Badge> : null}
        {values.length === 0 ? <span className="text-xs text-[var(--muted)]">—</span> : null}
      </div>
    </div>
  );
}

function DetailBlock({ label, value, asList = false }: { label: string; value: string; asList?: boolean }) {
  const items = asList ? splitList(value) : [];
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label}</p>
      {items.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {items.map((item) => (
            <Badge key={item} tone="neutral">
              {item}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink">{shown(value)}</p>
      )}
    </div>
  );
}

function IcpFields({ form }: { form: ReturnType<typeof useForm<ICPForm>> }) {
  return (
    <>
      <Field label="Name">
        <Input {...form.register("name", { required: true })} />
      </Field>
      <Field label="Industries">
        <Input {...form.register("industries")} placeholder="Comma-separated" />
      </Field>
      <Field label="Geographies">
        <Input {...form.register("geographies")} placeholder="Comma-separated" />
      </Field>
      <Field label="Min employees">
        <Input type="number" {...form.register("min_employees")} />
      </Field>
      <Field label="Max employees">
        <Input type="number" {...form.register("max_employees")} />
      </Field>
      <Field label="Personas">
        <Textarea rows={3} {...form.register("personas")} />
      </Field>
      <Field label="Seniorities">
        <Input {...form.register("seniorities")} />
      </Field>
      <Field label="Job functions">
        <Input {...form.register("job_functions")} />
      </Field>
      <Field label="Target companies">
        <Textarea rows={2} {...form.register("target_companies")} />
      </Field>
      <Field label="Keywords">
        <Input {...form.register("keywords")} />
      </Field>
      <Field label="Description">
        <Textarea rows={5} {...form.register("description")} />
      </Field>
      <CheckField label="Default profile" {...form.register("is_default")} />
    </>
  );
}

function IcpDialog({
  row,
  canEdit,
  onClose,
  onEdit,
}: {
  row: ICP;
  canEdit: boolean;
  onClose: () => void;
  onEdit: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="icp-detail-title" data-testid="icp-details">
      <button type="button" className="modal-scrim" aria-label="Close details" onClick={onClose} />
      <div className="modal-card" style={{ maxHeight: "min(760px, calc(100vh - 48px))", overflow: "auto" }}>
        <header className="modal-head">
          <h2 id="icp-detail-title">{row.name}</h2>
          {row.is_default ? <Badge tone="gold">Default</Badge> : null}
        </header>
        <div className="modal-body">
          <DetailBlock label="Description" value={row.description} />
          <DetailBlock label="Industries" value={row.industries} asList />
          <DetailBlock label="Geographies" value={row.geographies} asList />
          <div className="line-item">
            <span>Min employees</span>
            <span>{shown(row.min_employees)}</span>
          </div>
          <div className="line-item">
            <span>Max employees</span>
            <span>{shown(row.max_employees)}</span>
          </div>
          <DetailBlock label="Personas" value={row.personas || ""} />
          <DetailBlock label="Seniorities" value={row.seniorities || ""} asList />
          <DetailBlock label="Job functions" value={row.job_functions || ""} asList />
          <DetailBlock label="Target companies" value={row.target_companies || ""} />
          <DetailBlock label="Keywords" value={row.keywords || ""} asList />
          <div className="line-item">
            <span>Default profile</span>
            <span>{shown(row.is_default)}</span>
          </div>
        </div>
        <footer className="modal-foot">
          <Button variant="line" onClick={onClose}>
            Close
          </Button>
          {canEdit ? <Button onClick={onEdit}>Edit</Button> : null}
        </footer>
      </div>
    </div>
  );
}

export default function ICPsPage() {
  const { can, user } = useAuth();
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ICP | null>(null);
  const [viewing, setViewing] = useState<ICP | null>(null);
  const form = useForm<ICPForm>({ defaultValues: EMPTY_FORM });
  const canEdit = Boolean(
    user &&
      can("icps.write") &&
      (user.is_super_admin || user.roles.some((role) => EDITOR_ROLES.has(role.trim().toLowerCase()))),
  );
  const query = useQuery({
    queryKey: ["icps"],
    queryFn: async () => (await api<ICP[]>("/api/v1/icps")).data ?? [],
    enabled: can("icps.read"),
  });
  const save = useMutation({
    mutationFn: (body: ICPForm) => {
      const payload = toPayload(body);
      if (editing) {
        return api(`/api/v1/icps/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      }
      return api("/api/v1/icps", { method: "POST", body: JSON.stringify(payload) });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["icps"] });
      setCreating(false);
      setEditing(null);
      form.reset(EMPTY_FORM);
    },
  });
  const closeDetails = useCallback(() => setViewing(null), []);
  const openCreate = () => {
    setEditing(null);
    setViewing(null);
    form.reset(EMPTY_FORM);
    setCreating(true);
  };
  const openEdit = (row: ICP) => {
    setCreating(false);
    setViewing(null);
    form.reset(toForm(row));
    setEditing(row);
  };

  if (!can("icps.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState />;
  if (query.isError) return <ErrorState message="ICPs could not be assembled." />;
  const rows = query.data ?? [];
  const formOpen = creating || editing !== null;

  return (
    <div>
      <PageHeader
        eyebrow="Step 1 · Start here"
        title="Who we sell to"
        subtitle="Each profile keeps a short summary here. Open one to read the full record."
        actions={canEdit ? <Button onClick={openCreate}>Define an ICP</Button> : null}
      />
      {rows.length === 0 ? (
        <EmptyState title="No profile yet" body="Define industries, geography, and size so lead scoring has a house standard." />
      ) : (
        <section className="panel">
          <header className="panel-head">
            <h2>Profiles</h2>
          </header>
          <ul>
            {rows.map((row) => (
              <li key={row.id} className="row">
                <button
                  type="button"
                  className="connection-card main"
                  aria-haspopup="dialog"
                  onClick={() => setViewing(row)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <h3>{row.name}</h3>
                    {row.is_default ? <Badge tone="gold">Default</Badge> : null}
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <ChipRow label="Industries" values={splitList(row.industries)} />
                    <ChipRow label="Geographies" values={splitList(row.geographies)} />
                  </div>
                  <p className="mt-3 text-xs text-[var(--muted)]">
                    Min employees {shown(row.min_employees)}
                    {row.max_employees ? ` · Max employees ${row.max_employees}` : ""}
                  </p>
                </button>
                {canEdit ? (
                  <div className="row-actions">
                    <Button variant="line" onClick={() => openEdit(row)}>
                      Edit
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}
      {viewing ? (
        <IcpDialog row={viewing} canEdit={canEdit} onClose={closeDetails} onEdit={() => openEdit(viewing)} />
      ) : null}
      <Drawer
        open={formOpen}
        title={editing ? `Edit ${editing.name}` : "Define an ICP"}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
      >
        <form onSubmit={form.handleSubmit((values) => save.mutate(values))} className="space-y-4">
          <IcpFields form={form} />
          {save.isError ? <p className="text-sm text-[#e08b7a]">The profile was not saved.</p> : null}
          <FormActions
            pending={save.isPending}
            onCancel={() => {
              setCreating(false);
              setEditing(null);
            }}
            label={editing ? "Save changes" : "Save ICP"}
          />
        </form>
      </Drawer>
    </div>
  );
}
