"use client";

import { Button, Field, Input, Select, Textarea } from "@/components/ui";
import { useState } from "react";

export type DesignedField = {
  key: string;
  label: string;
  type: "text" | "email" | "tel" | "textarea" | "checkbox" | "select";
  required: boolean;
  placeholder: string;
  options: string[];
};

export type DesignedForm = {
  id?: string;
  name: string;
  fields: DesignedField[];
};

const LEAD_FIELDS: DesignedField[] = [
  { key: "first_name", label: "First name", type: "text", required: true, placeholder: "", options: [] },
  { key: "last_name", label: "Last name", type: "text", required: true, placeholder: "", options: [] },
  { key: "email", label: "Work email", type: "email", required: true, placeholder: "", options: [] },
  { key: "phone", label: "Phone", type: "tel", required: false, placeholder: "", options: [] },
  { key: "company_name", label: "Company", type: "text", required: false, placeholder: "", options: [] },
  { key: "title", label: "Role", type: "text", required: false, placeholder: "", options: [] },
  { key: "request_note", label: "What do you want?", type: "textarea", required: true, placeholder: "Describe what you want next.", options: [] },
  { key: "consent_email", label: "I agree to be contacted about this request.", type: "checkbox", required: true, placeholder: "", options: [] },
];

export function defaultFormFields(): DesignedField[] {
  return LEAD_FIELDS.map((field) => ({ ...field, options: [] }));
}

function customField(): DesignedField {
  const suffix = Math.random().toString(36).slice(2, 8).replace(/[^a-z0-9]/g, "a");
  return { key: `custom_${suffix}`, label: "Question", type: "text", required: false, placeholder: "", options: [] };
}

function move(fields: DesignedField[], index: number, direction: -1 | 1): DesignedField[] {
  const next = index + direction;
  if (next < 0 || next >= fields.length) return fields;
  const copy = fields.slice();
  const current = copy[index];
  const swap = copy[next];
  if (!current || !swap) return fields;
  copy[index] = swap;
  copy[next] = current;
  return copy;
}

function FieldPreview({ field }: { field: DesignedField }) {
  switch (field.type) {
    case "textarea":
      return <textarea className="input" rows={3} placeholder={field.placeholder} disabled />;
    case "checkbox":
      return (
        <label className="ds-flex small">
          <input type="checkbox" disabled />
          {field.label}
        </label>
      );
    case "select":
      return (
        <select className="input" disabled>
          <option>Select</option>
          {field.options.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      );
    case "text":
    case "email":
    case "tel":
      return <input className="input" type={field.type} placeholder={field.placeholder} disabled />;
    default: {
      const exhaustive: never = field.type;
      return exhaustive;
    }
  }
}

export function FormDesigner({
  initial,
  pending,
  error,
  onClose,
  onSave,
}: {
  initial: DesignedForm;
  pending: boolean;
  error: string;
  onClose: () => void;
  onSave: (value: DesignedForm) => void;
}) {
  const [name, setName] = useState(initial.name);
  const [fields, setFields] = useState<DesignedField[]>(initial.fields.length ? initial.fields : defaultFormFields());
  const used = new Set(fields.map((field) => field.key));
  const missingLead = ["first_name", "last_name", "email", "request_note", "consent_email"].filter((key) => !used.has(key));

  function update(index: number, patch: Partial<DesignedField>) {
    setFields((current) => current.map((field, item) => (item === index ? { ...field, ...patch } : field)));
  }

  return (
    <div className="modal">
      <button className="modal-scrim" type="button" aria-label="Close form designer" onClick={onClose} />
      <div className="modal-card form-designer" role="dialog" aria-modal="true" aria-labelledby="form-designer-title">
        <header className="form-designer-head">
          <h2 id="form-designer-title">{initial.id ? "Design form" : "Create form"}</h2>
          <Button type="button" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </header>
        <div className="form-designer-body">
          <div className="form-designer-editor">
            <Field label="Form purpose">
              <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Demo request" />
            </Field>
            <div className="form-designer-add">
              {LEAD_FIELDS.filter((field) => !used.has(field.key)).map((field) => (
                <Button key={field.key} type="button" variant="ghost" onClick={() => setFields((current) => [...current, { ...field }])}>
                  Add {field.label}
                </Button>
              ))}
              <Button type="button" variant="ghost" onClick={() => setFields((current) => [...current, customField()])}>
                Add question
              </Button>
            </div>
            <ul className="form-designer-fields">
              {fields.map((field, index) => (
                <li key={field.key}>
                  <Field label="Label">
                    <Input value={field.label} onChange={(event) => update(index, { label: event.target.value })} />
                  </Field>
                  {field.key.startsWith("custom_") ? (
                    <Field label="Answer">
                      <Select
                        value={field.type}
                        onChange={(event) => {
                          const type = event.target.value;
                          if (type === "text" || type === "textarea" || type === "select") {
                            update(index, { type, options: type === "select" ? field.options : [] });
                          }
                        }}
                      >
                        <option value="text">Short text</option>
                        <option value="textarea">Long text</option>
                        <option value="select">Choice list</option>
                      </Select>
                    </Field>
                  ) : null}
                  {field.type !== "checkbox" ? (
                    <Field label="Placeholder">
                      <Input value={field.placeholder} onChange={(event) => update(index, { placeholder: event.target.value })} />
                    </Field>
                  ) : null}
                  {field.type === "select" ? (
                    <Field label="Choices, one per line">
                      <Textarea
                        rows={3}
                        value={field.options.join("\n")}
                        onChange={(event) =>
                          update(index, {
                            options: event.target.value
                              .split("\n")
                              .map((option) => option.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </Field>
                  ) : null}
                  <label className="ds-flex small">
                    <input type="checkbox" checked={field.required} onChange={(event) => update(index, { required: event.target.checked })} />
                    Required
                  </label>
                  <div className="ds-flex">
                    <Button type="button" variant="ghost" onClick={() => setFields((current) => move(current, index, -1))}>
                      Up
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => setFields((current) => move(current, index, 1))}>
                      Down
                    </Button>
                    <Button type="button" variant="ghost" onClick={() => setFields((current) => current.filter((item) => item.key !== field.key))}>
                      Remove
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            {missingLead.length > 0 ? (
              <p className="small channel-preview-gap">
                A lead is created when first name, last name, email, a request, and consent are on the form and filled in.
              </p>
            ) : null}
            {error ? <p className="small channel-preview-gap">{error}</p> : null}
          </div>
          <aside className="form-designer-preview">
            <p className="upper">Preview</p>
            <h3>{name.trim() || "Untitled form"}</h3>
            <div className="stack">
              {fields.map((field) =>
                field.type === "checkbox" ? (
                  <FieldPreview key={field.key} field={field} />
                ) : (
                  <label className="field" key={field.key}>
                    <span>
                      {field.label || "Untitled"}
                      {field.required ? " *" : ""}
                    </span>
                    <FieldPreview field={field} />
                  </label>
                ),
              )}
            </div>
          </aside>
        </div>
        <footer className="form-designer-foot">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={pending || !name.trim() || fields.length === 0 || fields.some((field) => !field.label.trim() || (field.type === "select" && field.options.length === 0))}
            onClick={() => onSave({ id: initial.id, name: name.trim(), fields })}
          >
            {pending ? "Saving…" : "Save form"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
