"use client";

import { DograhTestPanel } from "@/components/dograh-test-panel";
import { PageHeader } from "@/components/page-header";
import { DeniedState } from "@/components/states";
import { useAuth } from "@/lib/auth";

export default function TestCallPage() {
  const { can } = useAuth();
  if (!can("conversations.read")) return <DeniedState />;
  return (
    <div>
      <PageHeader
        eyebrow="Sales"
        title="Test call"
        subtitle="Start a browser call with the Dograh voice agent. The microphone stays in this page, and no phone number is dialed."
      />
      <DograhTestPanel />
    </div>
  );
}
