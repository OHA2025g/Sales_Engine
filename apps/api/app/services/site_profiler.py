"""Read public website facts with regular expressions. No model, no browser.

A finding is recorded only from HTML already fetched. A missing page is an
empty result, never a guessed fact.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import unescape
from urllib.parse import urlparse

RECORD_FLOOR = 75
STALE_CONTENT_DAYS = 90

BENIGN_HOSTS = (
    "facebook.", "instagram.", "twitter.", "x.com", "linkedin.", "youtube.",
    "tiktok.", "pinterest.", "yelp.", "nextdoor.", "threads.",
    "google.com/maps", "g.page", "maps.app.goo.gl", "goo.gl", "wa.me",
    "bing.com/maps", "apple.com/maps",
    "greensky", "wellsfargo", "synchrony", "affirm", "klarna", "paypal",
    "stripe.com", "bbb.org", "angi.com", "homeadvisor", "houzz.",
    "trustpilot", "birdeye", "podium.com",
    "accessibe", "userway", "audioeye", "termly", "iubenda", "onetrust",
    "cloudflare", "godaddy", "wordpress.org", "wix.com", "squarespace.com",
    "shopify.com", "webflow.com", "duda.co", "gtranslate", "jquery",
    "gstatic", "googleapis", "cloudfront", "akamai", "w3.org", "schema.org",
)

STRONG_CREDIT = re.compile(
    r"\b(powered|website|site|web\s*design|designed|developed|built|created|marketing)\s+(by|&)\b",
    re.I,
)
DESCRIPTIVE_CREDIT = re.compile(
    r"\b(web\s*design|website\s*design|digital\s*marketing|seo|marketing\s*agency|web\s*development)\b",
    re.I,
)
TECH_FINGERPRINTS: dict[str, tuple[str, ...]] = {
    "WordPress": (r"wp-content/", r"wp-includes/"),
    "Shopify": (r"cdn\.shopify\.com", r"myshopify\.com"),
    "Wix": (r"static\.parastorage\.com",),
    "Squarespace": (r"static1\.squarespace\.com",),
    "Webflow": (r"assets\.website-files\.com", r"data-wf-domain"),
    "GoDaddy Website Builder": (r"img1\.wsimg\.com",),
    "HubSpot": (r"js\.hs-scripts\.com", r"js\.hsforms\.net"),
    "Google Analytics": (r"googletagmanager\.com/gtag", r"google-analytics\.com"),
    "Google Tag Manager": (r"googletagmanager\.com/gtm\.js",),
    "Intercom": (r"widget\.intercom\.io",),
    "Calendly": (r"assets\.calendly\.com",),
    "Stripe": (r"js\.stripe\.com",),
}
GOOGLE_ADS = (r"googleadservices\.com", r"gtag/js\?id=AW-", r"google_conversion")
META_PIXEL = (r"connect\.facebook\.net/[^\"']*fbevents\.js", r"fbq\s*\(\s*['\"]init")
BOOKING_HINTS = (
    r"calendly\.com", r"acuityscheduling", r"schedulicity", r"setmore",
    r"book(?:ing)?[-_]?now", r"schedule[-_]?(?:an?[-_])?(?:appointment|estimate|consultation)",
)
AI_CRAWLERS = ("gptbot", "google-extended", "ccbot", "anthropic-ai", "claudebot", "perplexitybot", "bytespider")
DECISION_TITLES = (
    "owner", "founder", "co-founder", "president", "ceo", "principal", "partner",
    "general manager", "marketing director", "director of marketing", "vice president",
    "managing director", "chief",
)
ROLE_HINT = re.compile(
    r"\b(owner|founder|president|ceo|principal|partner|manager|director|sales|marketing|operations|office)\b",
    re.I,
)
NON_NAME_WORDS = frozenset(
    "service services about contact team staff company home page site our your the and".split()
)


@dataclass(frozen=True)
class RawObservation:
    code: str
    value_num: int | None
    value_text: str
    confidence: int
    evidence_url: str


def strip_code(html: str) -> str:
    html = re.sub(r"(?is)<script\b.*?</script>", " ", html)
    html = re.sub(r"(?is)<style\b.*?</style>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    return html


def _any(html: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, html, re.I) for pattern in patterns)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def detect_agency(html: str, domain: str, page_url: str) -> RawObservation | None:
    cleaned = strip_code(html)
    footer = re.search(r"(?is)<footer\b.*?</footer>", cleaned)
    region = footer.group(0) if footer else cleaned[-12000:]
    best: tuple[str, int, str] | None = None
    for link in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', region):
        href = link.group(1)
        anchor = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", link.group(2))).strip()
        if not href.startswith("http") or not anchor or len(anchor) > 80:
            continue
        host = _host(href)
        if not host or host == domain or host.endswith(f".{domain}") or domain.endswith(f".{host}"):
            continue
        blob_href = href.lower()
        if any(marker in blob_href or marker in host for marker in BENIGN_HOSTS):
            continue
        start = max(0, link.start() - 120)
        context = re.sub(r"(?s)<[^>]+>", " ", region[start:link.start()])
        blob = f"{context} {anchor}"
        if STRONG_CREDIT.search(blob):
            confidence = 90
        elif DESCRIPTIVE_CREDIT.search(anchor):
            confidence = 75
        else:
            confidence = 35
        if confidence >= RECORD_FLOOR and (best is None or confidence > best[1]):
            best = (anchor[:80], confidence, href[:1000])
    if best is None:
        return None
    return RawObservation("INCUMBENT_AGENCY", None, best[0], best[1], best[2] or page_url)


def detect_tech(html: str) -> list[str]:
    found = [name for name, patterns in TECH_FINGERPRINTS.items() if _any(html, patterns)]
    return sorted(found)


def _name_ok(name: str) -> bool:
    parts = name.split()
    if len(parts) < 2 or len(name) > 45 or re.search(r"\d|@", name):
        return False
    return all(part.lower() not in NON_NAME_WORDS for part in parts)


def detect_people(html: str, page_url: str) -> list[RawObservation]:
    cleaned = strip_code(html)
    found: list[RawObservation] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"(?s)<((?i:h[1-5]|strong|b))[^>]*>\s*([A-Z][a-z'\-]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z'\-]+)\s*</(?i:\1)>"
    )
    for match in pattern.finditer(cleaned):
        name = re.sub(r"\s+", " ", match.group(2)).strip()
        key = name.lower()
        if key in seen or not _name_ok(name):
            continue
        window = cleaned[match.end():match.end() + 180]
        title_match = ROLE_HINT.search(unescape(re.sub(r"(?s)<[^>]+>", " ", window)))
        if not title_match:
            continue
        title = re.sub(r"\s+", " ", title_match.group(0)).strip()[:80]
        seen.add(key)
        label = f"{name} — {title}"
        found.append(RawObservation("CONTACT_FOUND", None, label, 70, page_url))
        if any(token in title.lower() for token in DECISION_TITLES):
            found.append(RawObservation("DECISION_MAKER_TITLE", None, label, 70, page_url))
        if len(seen) >= 8:
            break
    return found


def detect_roles(html: str, page_url: str) -> list[RawObservation]:
    roles: list[RawObservation] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?is)<(h[2-5]|a|li)[^>]*>\s*([^<]{6,70})\s*</\1>", strip_code(html)):
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        if title.lower() in seen:
            continue
        if not re.search(r"\b(hiring|apply|position|opening|technician|installer|sales|manager|estimator)\b", title, re.I):
            continue
        seen.add(title.lower())
        roles.append(RawObservation("HIRING_ROLE", None, title[:80], 70, page_url))
        if len(roles) >= 3:
            break
    return roles


def _has_form(html: str) -> bool:
    return bool(re.search(r"(?is)<form\b", strip_code(html)))


def analyze_pages(
    *,
    domain: str,
    home_url: str,
    home: str,
    robots: str,
    robots_url: str,
    sitemap: str,
    sitemap_url: str,
    team: str,
    team_url: str,
    careers: str,
    careers_url: str,
    contact: str,
    contact_url: str,
    wanted: set[str],
    today: date | None = None,
) -> list[RawObservation]:
    """Signals present in the pages, limited to codes the tenant confirmed."""
    found: list[RawObservation] = []
    if not home:
        return found
    if "RUNNING_GOOGLE_ADS" in wanted:
        found.append(RawObservation("RUNNING_GOOGLE_ADS", 1 if _any(home, GOOGLE_ADS) else 0, "", 100, home_url))
    if "RUNNING_META_ADS" in wanted:
        found.append(RawObservation("RUNNING_META_ADS", 1 if _any(home, META_PIXEL) else 0, "", 100, home_url))
    if "TECH_STACK" in wanted:
        tech = detect_tech(home)
        if tech:
            found.append(RawObservation("TECH_STACK", None, ", ".join(tech)[:400], 80, home_url))
    if "NO_SCHEMA_MARKUP" in wanted:
        has_schema = bool(re.search(r"application/ld\+json", home, re.I) and re.search(r'"@type"', home))
        found.append(RawObservation("NO_SCHEMA_MARKUP", 0 if has_schema else 1, "", 100, home_url))
    if "NO_ONLINE_BOOKING" in wanted:
        found.append(RawObservation("NO_ONLINE_BOOKING", 0 if _any(home, BOOKING_HINTS) else 1, "", 100, home_url))
    if "INCUMBENT_AGENCY" in wanted:
        agency = detect_agency(home, domain, home_url)
        if agency is not None:
            found.append(agency)
    if "BLOCKS_AI_CRAWLERS" in wanted and robots:
        blocked = any(
            re.search(rf"user-agent:\s*{re.escape(bot)}[\s\S]{{0,200}}?disallow:\s*/", robots, re.I)
            for bot in AI_CRAWLERS
        )
        found.append(RawObservation("BLOCKS_AI_CRAWLERS", 1 if blocked else 0, "", 100, robots_url))
    if sitemap and ({"SITE_PAGE_COUNT", "BLOG_STALE"} & wanted):
        locs = re.findall(r"<loc>\s*([^<]+)\s*</loc>", sitemap)
        if "SITE_PAGE_COUNT" in wanted and locs:
            found.append(RawObservation("SITE_PAGE_COUNT", min(len(locs), 5000), "", 90, sitemap_url))
        if "BLOG_STALE" in wanted:
            dates = re.findall(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})", sitemap)
            if dates:
                newest = max(dates)
                try:
                    age = ((today or datetime.now(timezone.utc).date()) - date.fromisoformat(newest)).days
                except ValueError:
                    age = -1
                if age >= 0:
                    stale = age >= STALE_CONTENT_DAYS
                    found.append(RawObservation(
                        "BLOG_STALE",
                        age if stale else 0,
                        newest if stale else "",
                        90,
                        sitemap_url,
                    ))
    if "CONTACT_FORM_URL" in wanted:
        if _has_form(home):
            found.append(RawObservation("CONTACT_FORM_URL", None, home_url[:400], 80, home_url))
        elif contact and _has_form(contact):
            found.append(RawObservation("CONTACT_FORM_URL", None, contact_url[:400], 80, contact_url))
    if "HIRING_ROLE" in wanted and careers:
        found.extend(detect_roles(careers, careers_url))
    if {"CONTACT_FOUND", "DECISION_MAKER_TITLE"} & wanted and team:
        for person in detect_people(team, team_url):
            if person.code in wanted:
                found.append(person)
    return [item for item in found if item.code in wanted]
