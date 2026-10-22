"""The website-signal catalog Harvey uses, adapted as an additive reader.

Nothing in this catalog is collected until a person confirms it. Signals
marked collectable are read from public pages or from the account record.
The rest stay visible so a person can see the full vocabulary, and the free
reader never invents a value for them.
"""

from dataclasses import dataclass

STATUSES = ("proposed", "confirmed", "skipped", "rejected")
DECISIONS = ("confirmed", "skipped", "rejected")
STALE_DAYS = 90


@dataclass(frozen=True)
class SignalSpec:
    code: str
    label: str
    description: str
    category: str
    value_type: str
    cost_note: str
    collectable: bool


CATALOG: tuple[SignalSpec, ...] = (
    SignalSpec("SERP_RANK", "Search rank position", "Where the business ranks for its own core search. Positions 11–30 are the useful band.", "discovery", "num", "Paid search lookup. Not read by the free website reader.", False),
    SignalSpec("FOUND_IN_SERP", "Discovered via search", "The business appeared in a target-market search.", "discovery", "text", "Included in a paid search lookup. Not read by the free website reader.", False),
    SignalSpec("NO_WEBSITE", "No website at all", "The account has a name and no public site on file.", "discovery", "bool", "Free. Read from the account record.", True),
    SignalSpec("UNCLAIMED_LISTING", "Unclaimed Google listing", "Nobody has claimed their Google Business Profile.", "discovery", "bool", "Included in a business-listing lookup. Not read by the free website reader.", False),
    SignalSpec("REVIEW_RATING", "Review rating", "Average star rating from a business listing.", "discovery", "num", "Included in a business-listing lookup. Not read by the free website reader.", False),
    SignalSpec("REVIEW_COUNT", "Number of reviews", "How many reviews a listing shows.", "discovery", "num", "Included in a business-listing lookup. Not read by the free website reader.", False),
    SignalSpec("INCUMBENT_AGENCY", "Has a marketing or web agency", "An agency credited in the site footer. Recorded only when the credit wording is explicit.", "profile", "text", "Free. Homepage HTML.", True),
    SignalSpec("RUNNING_GOOGLE_ADS", "Running Google Ads", "A Google Ads tag is on the homepage, so they are spending on acquisition.", "profile", "bool", "Free. Homepage HTML.", True),
    SignalSpec("RUNNING_META_ADS", "Running Meta ads", "A Meta pixel is on the homepage.", "profile", "bool", "Free. Homepage HTML.", True),
    SignalSpec("TECH_STACK", "Website platform", "Platform and tools detected on the homepage, such as WordPress, Shopify, or HubSpot.", "profile", "text", "Free. Homepage HTML.", True),
    SignalSpec("NO_SCHEMA_MARKUP", "Missing structured data", "The homepage has no JSON-LD schema.", "profile", "bool", "Free. Homepage HTML.", True),
    SignalSpec("NO_ONLINE_BOOKING", "No online booking", "No booking or scheduling widget on the homepage.", "profile", "bool", "Free. Homepage HTML.", True),
    SignalSpec("SITE_PAGE_COUNT", "Site size", "Page count from sitemap.xml.", "profile", "num", "Free. sitemap.xml.", True),
    SignalSpec("BLOG_STALE", "Content gone stale", "Newest sitemap date is at least 90 days old.", "profile", "num", "Free. sitemap.xml.", True),
    SignalSpec("BLOCKS_AI_CRAWLERS", "Blocks AI crawlers", "robots.txt disallows an AI crawler for the whole site.", "profile", "bool", "Free. robots.txt.", True),
    SignalSpec("HIRING_ROLE", "Hiring for a role", "An open role named on the careers page.", "profile", "text", "Free. Careers page.", True),
    SignalSpec("CONTACT_FOUND", "Named contact found", "A named person and title on the team page.", "people", "text", "Free. Team page.", True),
    SignalSpec("DECISION_MAKER_TITLE", "Decision-maker title", "A team-page title that reads like an owner or director.", "people", "text", "Free. Team page.", True),
    SignalSpec("REGISTRY_VERIFIED", "Confirmed in a public registry", "A person confirmed against a public registry.", "people", "text", "Needs a registry source. Not read by the free website reader.", False),
    SignalSpec("LIKELY_OWNER", "Likely the owner", "Registry evidence that this person owns the business.", "people", "bool", "Needs a registry source. Not read by the free website reader.", False),
    SignalSpec("EMAIL_PATTERN", "Company email pattern", "The domain's address format.", "verification", "text", "Needs an email-pattern source. Not read by the free website reader.", False),
    SignalSpec("EMAIL_STATUS", "Email deliverability", "Whether an address is verified, catch-all, a guess, or invalid.", "verification", "text", "Needs a verifier. Not read by the free website reader.", False),
    SignalSpec("CONTACT_FORM_URL", "Contact form available", "A contact form on the site, so the business can be reached without an email address.", "verification", "text", "Free. Site HTML.", True),
)

BY_CODE = {spec.code: spec for spec in CATALOG}

OPENING_ORDER = (
    "INCUMBENT_AGENCY",
    "RUNNING_GOOGLE_ADS",
    "RUNNING_META_ADS",
    "NO_ONLINE_BOOKING",
    "NO_SCHEMA_MARKUP",
    "HIRING_ROLE",
    "BLOG_STALE",
    "NO_WEBSITE",
    "CONTACT_FORM_URL",
    "DECISION_MAKER_TITLE",
    "CONTACT_FOUND",
    "TECH_STACK",
    "BLOCKS_AI_CRAWLERS",
    "SITE_PAGE_COUNT",
)


def opening_line(code: str, value_text: str, value_num: int | None) -> str:
    """One factual sentence from a confirmed observation. No model call."""
    text = (value_text or "").strip()
    if code == "INCUMBENT_AGENCY" and text:
        return f"Their site credits {text}."
    if code == "RUNNING_GOOGLE_ADS":
        return "Their homepage loads a Google Ads tag."
    if code == "RUNNING_META_ADS":
        return "Their homepage loads a Meta pixel."
    if code == "NO_ONLINE_BOOKING":
        return "Their homepage has no online booking widget."
    if code == "NO_SCHEMA_MARKUP":
        return "Their homepage has no JSON-LD schema."
    if code == "HIRING_ROLE" and text:
        return f"Their careers page lists {text}."
    if code == "BLOG_STALE" and text:
        return f"Their newest sitemap date is {text}."
    if code == "NO_WEBSITE":
        return "This account has no website on file."
    if code == "CONTACT_FORM_URL":
        return "They publish a contact form."
    if code in {"DECISION_MAKER_TITLE", "CONTACT_FOUND"} and text:
        return f"Their team page names {text}."
    if code == "TECH_STACK" and text:
        return f"Their site runs {text}."
    if code == "BLOCKS_AI_CRAWLERS":
        return "Their robots.txt blocks an AI crawler."
    if code == "SITE_PAGE_COUNT" and value_num is not None:
        return f"Their sitemap lists {value_num} pages."
    return ""
