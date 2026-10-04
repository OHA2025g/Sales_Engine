"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const ROLE_PREVIEWS = [
  "Revenue manager",
  "Marketing manager",
  "Account executive",
  "Sales development",
  "Customer success",
] as const;

export type RolePreview = (typeof ROLE_PREVIEWS)[number];

const STORAGE_KEY = "sales-engine-role-preview";

type RoleState = {
  role: RolePreview;
  setRole: (role: RolePreview) => void;
};

const RoleContext = createContext<RoleState | null>(null);

function isRole(value: string): value is RolePreview {
  return (ROLE_PREVIEWS as readonly string[]).includes(value);
}

export function RolePreviewProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<RolePreview>("Revenue manager");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && isRole(stored)) setRoleState(stored);
  }, []);

  const value = useMemo<RoleState>(
    () => ({
      role,
      setRole: (next) => {
        setRoleState(next);
        window.localStorage.setItem(STORAGE_KEY, next);
      },
    }),
    [role],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRolePreview(): RoleState {
  const value = useContext(RoleContext);
  if (!value) return { role: "Revenue manager", setRole: () => undefined };
  return value;
}

export function roleFocus(role: RolePreview): string {
  switch (role) {
    case "Revenue manager":
      return "Qualified pipeline, accepted business, and the decisions that change either one.";
    case "Marketing manager":
      return "Campaign outcomes and the journeys that can actually send.";
    case "Sales development":
      return "Eligibility, consent, and the next human step on each lead.";
    case "Account executive":
      return "Stage evidence, quotes, and the commercial decision in front of you.";
    case "Customer success":
      return "Onboarding, renewal risk, and health that is still unavailable.";
    default: {
      const neverRole: never = role;
      return neverRole;
    }
  }
}
