"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { useAuth } from "@/lib/auth";
import { when } from "@/lib/format";
import type { Meeting } from "@/lib/types";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

export default function CalendarPage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["meetings"],
    queryFn: async () => (await api<Meeting[]>("/api/v1/lifecycle/meetings")).data ?? [],
    enabled: can("meetings.read"),
  });
  if (!can("meetings.read")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading the calendar" />;
  if (query.isError) return <ErrorState message="Meetings could not be loaded." />;
  const rows = query.data ?? [];
  const scheduled = rows.filter((row) => row.start_at);
  const open = rows.filter((row) => !row.start_at);
  return (
    <div>
      <PageHeader
        eyebrow="Marketing"
        title="Calendar"
        subtitle="Scheduled meetings from this tenant. A meeting without a start time stays unscheduled."
        nextHref="/acquisition"
        nextLabel="Inbound"
      />
      <section className="panel">
        <header className="panel-head">
          <h2>Scheduled work</h2>
          <span className="tag">{rows.length} records</span>
        </header>
        {rows.length === 0 ? (
          <div className="empty">
            <h3>Nothing scheduled</h3>
            <p>Log a meeting before it can appear on the calendar.</p>
          </div>
        ) : (
          <div className="calendar-grid">
            {scheduled.map((row) => (
              <div className="calendar-day" key={row.id}>
                <div className="day-label">{when(row.start_at)}</div>
                <Link className="calendar-event" href={`/meetings/${row.id}`}>
                  {row.title}
                  <p>{row.status || "Meeting"}</p>
                </Link>
              </div>
            ))}
            {open.map((row) => (
              <div className="calendar-day" key={row.id}>
                <div className="day-label">Unscheduled</div>
                <Link className="calendar-event" href={`/meetings/${row.id}`}>
                  {row.title}
                  <p>Start time unavailable</p>
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
