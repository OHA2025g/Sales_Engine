"use client";

import { getApiBase } from "@agrayian/sdk";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

type Attribution = {
  utm_source: string;
  utm_medium: string;
  utm_campaign: string;
  campaign_id: string;
  ad_id: string;
};

export default function PublicCapturePage() {
  const params = useParams<{ token: string }>();
  const token = String(params.token || "");
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState(false);
  const [attribution, setAttribution] = useState<Attribution>({
    utm_source: "",
    utm_medium: "",
    utm_campaign: "",
    campaign_id: "",
    ad_id: "",
  });

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    setAttribution({
      utm_source: query.get("utm_source") || "",
      utm_medium: query.get("utm_medium") || "",
      utm_campaign: query.get("utm_campaign") || "",
      campaign_id: query.get("campaign_id") || "",
      ad_id: query.get("ad_id") || query.get("adid") || "",
    });
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setStatus("");
    const data = Object.fromEntries(new FormData(event.currentTarget).entries());
    const api = getApiBase();
    const response = await fetch(`${api}/api/v1/public/forms/${token}/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        first_name: data.first_name,
        last_name: data.last_name,
        email: data.email,
        company_name: data.company_name,
        consent_email: data.consent_email === "true",
        utm_source: attribution.utm_source,
        utm_medium: attribution.utm_medium,
        utm_campaign: attribution.utm_campaign,
        campaign_id: attribution.campaign_id || null,
        ad_id: attribution.ad_id,
      }),
    });
    setPending(false);
    setStatus(response.ok ? "Received. A human will follow only if you consented." : "This form could not be submitted.");
  }

  return (
    <main className="capture-page">
      <section className="panel capture-card">
        <div className="public-brand">
          <span className="brand-mark"><i /><i /><i /></span>
          AGRAYIAN AI LABS
        </div>
        <div className="eyebrow">Inbound</div>
        <h1>Discuss your operational workflow</h1>
        <p className="muted" style={{ margin: "15px 0 26px" }}>
          Share the process you want to improve. A human follows only if you consent.
        </p>
        <form className="stack" onSubmit={submit}>
          <div className="form-grid">
            <label className="field">First name<input name="first_name" required autoComplete="given-name" /></label>
            <label className="field">Last name<input name="last_name" required autoComplete="family-name" /></label>
            <label className="field">Work email<input name="email" type="email" required autoComplete="email" /></label>
            <label className="field">Company<input name="company_name" autoComplete="organization" /></label>
          </div>
          <label className="ds-flex small muted">
            <input className="checkbox" type="checkbox" name="consent_email" value="true" />
            I agree to be contacted about this request.
          </label>
          <button className="btn primary" disabled={pending} type="submit">
            {pending ? "Submitting…" : "Submit request"}
          </button>
        </form>
        {status ? <p className="small" style={{ marginTop: 16 }}>{status}</p> : null}
      </section>
    </main>
  );
}
