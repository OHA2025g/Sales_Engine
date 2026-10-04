"use client";

import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui";
import { StatusPill } from "@/components/workspace-ui";

export default function DesignSystemPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="Design system"
        subtitle="Empty, loading, failure, and completed states use the same labels as the workspace."
        nextHref="/screens"
        nextLabel="All page designs"
      />
      <div className="mb-6 flex flex-wrap gap-2">
        <StatusPill tone="success">Completed</StatusPill>
        <StatusPill tone="review">Needs review</StatusPill>
        <StatusPill tone="blocked">Blocked</StatusPill>
        <StatusPill tone="info">In progress</StatusPill>
        <Button>Primary action</Button>
        <Button variant="line">Secondary</Button>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <EmptyState title="Nothing here yet" body="The first action is to add a record. An empty list is not a zero metric." />
        <LoadingState label="Loading a record" />
        <ErrorState message="The source did not respond." />
        <div className="panel p-5 text-sm text-[var(--muted)]">Completed work shows the observed outcome. Approval alone is not success.</div>
      </div>
    </div>
  );
}
