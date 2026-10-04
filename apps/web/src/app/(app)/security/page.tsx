"use client";

import { PageHeader } from "@/components/page-header";
import { DeniedState, ErrorState, LoadingState } from "@/components/states";
import { StatusPill } from "@/components/workspace-ui";
import { useAuth } from "@/lib/auth";
import { api } from "@agrayian/sdk";
import { useQuery } from "@tanstack/react-query";

type Operations = {
  sso: string;
  whatsapp: string;
  emergency_stop: boolean;
  social_paused: boolean;
};

export default function SecurityPage() {
  const { can } = useAuth();
  const query = useQuery({
    queryKey: ["operations"],
    queryFn: async () => (await api<Operations>("/api/v1/workflow/operations")).data,
    enabled: can("pilot.view"),
  });
  if (!can("pilot.view")) return <DeniedState />;
  if (query.isLoading) return <LoadingState label="Loading security" />;
  if (query.isError || !query.data) return <ErrorState message="The operating snapshot could not be loaded." />;
  const data = query.data;
  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="Security"
        subtitle="SSO stays labeled not configured until a provider is connected. WhatsApp stays mock or not configured."
        nextHref="/design-system"
        nextLabel="Design system"
      />
      <ul className="panel space-y-3 p-5 text-sm">
        <li className="flex items-center justify-between"><span>Single sign-on</span><StatusPill tone="neutral">{data.sso}</StatusPill></li>
        <li className="flex items-center justify-between"><span>WhatsApp</span><StatusPill tone="neutral">{data.whatsapp}</StatusPill></li>
        <li className="flex items-center justify-between"><span>Emergency stop</span><StatusPill tone={data.emergency_stop ? "blocked" : "success"}>{data.emergency_stop ? "On" : "Clear"}</StatusPill></li>
        <li className="flex items-center justify-between"><span>Social channel</span><StatusPill tone={data.social_paused ? "review" : "success"}>{data.social_paused ? "Paused" : "Open"}</StatusPill></li>
      </ul>
    </div>
  );
}
