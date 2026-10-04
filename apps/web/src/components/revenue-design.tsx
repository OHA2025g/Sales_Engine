"use client";

import { useEffect } from "react";

declare global {
  interface Window {
    __revenueDesignLoaded?: boolean;
    __AGRAYIAN_API_URL?: string;
  }
}

function screenFromPath(path: string): string {
  const exact: Record<string, string> = {
    "/": "home",
    "/login": "login",
    "/flow": "flow",
    "/strategy": "strategy",
    "/icps": "icps",
    "/market": "market",
    "/market/signals": "signals",
    "/market/triggers": "triggers",
    "/campaigns": "campaigns",
    "/content": "content",
    "/social": "social",
    "/calendar": "calendar",
    "/acquisition": "acquisition",
    "/leads": "leads",
    "/accounts": "accounts",
    "/contacts": "contacts",
    "/imports": "imports",
    "/sequences": "sequences",
    "/sequences/builder": "sequence-builder",
    "/conversations": "conversations",
    "/meetings": "meetings",
    "/pipeline": "pipeline",
    "/deals": "deals",
    "/tasks": "tasks",
    "/commercial": "commercial",
    "/commercial/proposal": "proposal",
    "/commercial/contracts": "contracts",
    "/customers": "customers",
    "/onboarding": "onboarding",
    "/success": "success",
    "/renewals": "renewals",
    "/expansion": "expansion",
    "/advocacy": "advocacy",
    "/automation/runs": "runs",
    "/automation/approvals": "approvals",
    "/automation/voice-scripts": "voice",
    "/playbooks": "playbooks",
    "/playbooks/builder": "playbook-builder",
    "/policies": "policies",
    "/forecast": "forecast",
    "/insights/attribution": "attribution",
    "/insights/retention": "retention",
    "/insights/automation": "automation",
    "/intelligence": "intelligence",
    "/settings/company": "company",
    "/setup": "setup",
    "/launch": "setup",
    "/knowledge": "knowledge",
    "/models": "models",
    "/admin/integrations": "integrations",
    "/admin/users": "users",
    "/admin/teams": "teams",
    "/admin/flags": "flags",
    "/admin/audit": "audit",
    "/admin/pilot": "pilot",
    "/security": "security",
    "/design-system": "design-system",
    "/screens": "screen-index",
  };
  if (exact[path]) return exact[path];
  if (path.startsWith("/capture")) return "capture";
  if (path.startsWith("/leads/")) return "lead-detail";
  if (path.startsWith("/accounts/")) return "account-detail";
  if (path.startsWith("/contacts/")) return "contact-detail";
  if (path.startsWith("/market/")) return "market-detail";
  if (path.startsWith("/campaigns/")) return "campaign-detail";
  if (path.startsWith("/content/")) return "content-editor";
  if (path.startsWith("/meetings/")) return "meeting-detail";
  if (path.startsWith("/commercial/quotes/")) return "quote-detail";
  if (path.startsWith("/commercial/contracts/")) return "contract-detail";
  if (path.startsWith("/customers/")) return "customer-detail";
  if (path.startsWith("/renewals/")) return "renewal-detail";
  if (path.startsWith("/automation/runs/")) return "run-detail";
  if (path.startsWith("/tasks/")) return "task-detail";
  if (path.startsWith("/opportunities/")) return "opportunity-detail";
  if (path.startsWith("/coming-soon")) return "coming-soon";
  return "home";
}

export function RevenueDesign() {
  useEffect(() => {
    if (window.__revenueDesignLoaded) return;
    window.__revenueDesignLoaded = true;

    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/revenue-design/style.css?v=record-forms";
    document.head.appendChild(css);

    window.__AGRAYIAN_API_URL = "http://localhost:8000";

    if (!window.location.hash) {
      window.location.hash = `/${screenFromPath(window.location.pathname.replace(/\/$/, "") || "/")}`;
    }

    const data = document.createElement("script");
    data.src = "/revenue-design/data.js";
    data.onload = () => {
      const forms = document.createElement("script");
      forms.src = "/revenue-design/forms.js?v=record-forms";
      forms.onload = () => {
        const app = document.createElement("script");
        app.src = "/revenue-design/app.js?v=connection-card";
        document.body.appendChild(app);
      };
      document.body.appendChild(forms);
    };
    document.body.appendChild(data);
  }, []);

  return (
    <>
      <div id="app" />
      <div id="toast" role="status" aria-live="polite" />
      <dialog id="modal" aria-labelledby="modal-title" />
    </>
  );
}
