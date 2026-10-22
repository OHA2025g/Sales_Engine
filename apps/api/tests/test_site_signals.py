from datetime import date

from app.services.site_profiler import analyze_pages
from app.services.site_signals import fetch_public_text
from tests.conftest import login

HOME = """
<html><body>
<script src="https://www.googletagmanager.com/gtag/js?id=AW-123"></script>
<footer>Website by <a href="https://brightagency.example">Bright Agency</a></footer>
<p><a href="https://facebook.com/cascade">Facebook</a></p>
</body></html>
"""
TEAM = "<html><body><h2>Ada Lovelace</h2><p>Owner of the practice and the person who decides.</p></body></html>"


def test_homepage_facts_are_read_from_html_and_a_bare_link_is_not_an_agency() -> None:
    found = analyze_pages(
        domain="cascade.example",
        home_url="https://cascade.example/",
        home=HOME,
        robots="User-agent: GPTBot\nDisallow: /\n",
        robots_url="https://cascade.example/robots.txt",
        sitemap="<urlset><url><loc>https://cascade.example/a</loc><lastmod>2020-01-01</lastmod></url></urlset>",
        sitemap_url="https://cascade.example/sitemap.xml",
        team=TEAM,
        team_url="https://cascade.example/team",
        careers="<html><li>Hiring installer</li></html>",
        careers_url="https://cascade.example/careers",
        contact="",
        contact_url="",
        wanted={
            "RUNNING_GOOGLE_ADS",
            "RUNNING_META_ADS",
            "INCUMBENT_AGENCY",
            "NO_SCHEMA_MARKUP",
            "NO_ONLINE_BOOKING",
            "BLOCKS_AI_CRAWLERS",
            "BLOG_STALE",
            "HIRING_ROLE",
            "CONTACT_FOUND",
            "DECISION_MAKER_TITLE",
        },
        today=date(2026, 10, 21),
    )
    by_code = {item.code: item for item in found}
    assert by_code["RUNNING_GOOGLE_ADS"].value_num == 1
    assert by_code["RUNNING_META_ADS"].value_num == 0
    assert by_code["INCUMBENT_AGENCY"].value_text == "Bright Agency"
    assert by_code["NO_SCHEMA_MARKUP"].value_num == 1
    assert by_code["NO_ONLINE_BOOKING"].value_num == 1
    assert by_code["BLOCKS_AI_CRAWLERS"].value_num == 1
    assert by_code["BLOG_STALE"].value_num > 90
    assert by_code["HIRING_ROLE"].value_text == "Hiring installer"
    assert "Ada Lovelace" in by_code["CONTACT_FOUND"].value_text
    assert "DECISION_MAKER_TITLE" in by_code


def test_private_addresses_are_not_fetched() -> None:
    assert fetch_public_text("http://127.0.0.1/secret") == ""
    assert fetch_public_text("http://169.254.169.254/latest") == ""


def test_confirmed_signals_become_a_cohort_and_a_factual_line(client, monkeypatch) -> None:
    def fake_fetch(url: str) -> str:
        if "cascade.example" in url and url.rstrip("/").endswith("cascade.example"):
            return HOME
        if url.endswith("/team"):
            return TEAM if "cascade.example" in url else ""
        return ""

    monkeypatch.setattr("app.services.site_signals.fetch_public_text", fake_fetch)
    headers = login(client)
    created = client.post(
        "/api/v1/accounts",
        headers=headers,
        json={"name": "Cascade Landscaping", "website": "https://cascade.example"},
    )
    assert created.status_code == 200, created.text
    confirmed = client.post(
        "/api/v1/site-signals/status",
        headers=headers,
        json={"codes": ["INCUMBENT_AGENCY", "RUNNING_GOOGLE_ADS", "NO_SCHEMA_MARKUP"], "status": "confirmed"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert any(row["code"] == "SERP_RANK" and row["collectable"] is False for row in confirmed.json()["data"]["signals"])
    read = client.post("/api/v1/site-signals/profile", headers=headers, json={"limit": 25, "force": True})
    assert read.status_code == 200, read.text
    counted = client.post(
        "/api/v1/site-signals/cohort",
        headers=headers,
        json={"require": ["INCUMBENT_AGENCY", "RUNNING_GOOGLE_ADS"], "exclude": []},
    )
    assert counted.status_code == 200, counted.text
    body = counted.json()["data"]
    match = next(item for item in body["accounts"] if item["name"] == "Cascade Landscaping")
    assert match["opening"] == "Their site credits Bright Agency."
    other = login(client, "admin@northline.demo")
    hidden = client.post(
        "/api/v1/site-signals/cohort",
        headers=other,
        json={"require": ["INCUMBENT_AGENCY"], "exclude": []},
    )
    assert hidden.status_code == 200
    assert all(item["name"] != "Cascade Landscaping" for item in hidden.json()["data"]["accounts"])
    denied = client.post(
        "/api/v1/site-signals/profile",
        headers=login(client, "readonly@agrayian.demo"),
        json={"limit": 1},
    )
    assert denied.status_code == 403
