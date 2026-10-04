from app.models.crm import ICP
from app.providers.lead_discovery import DiscoveryQuery

SENIORITY_IDS = {
    "training": "100",
    "in training": "100",
    "entry": "110",
    "entry level": "110",
    "junior": "110",
    "senior": "120",
    "strategic": "130",
    "manager": "200",
    "entry level manager": "200",
    "experienced manager": "210",
    "director": "220",
    "vp": "300",
    "vice president": "300",
    "cxo": "310",
    "c-level": "310",
    "cio": "310",
    "cto": "310",
    "ceo": "310",
    "owner": "320",
    "partner": "320",
}

INDUSTRY_IDS = {
    "technology": "4",
    "software": "4",
    "it": "6",
    "enterprise": "6",
    "bfsi": "43",
    "finance": "43",
    "financial services": "43",
    "healthcare": "14",
    "manufacturing": "25",
    "retail": "27",
    "government": "75",
}

HEADCOUNT = (
    ("B", 1, 10),
    ("C", 11, 50),
    ("D", 51, 200),
    ("E", 201, 500),
    ("F", 501, 1000),
    ("G", 1001, 5000),
    ("H", 5001, 10000),
    ("I", 10001, 10_000_000),
)

FUNCTION_IDS = {
    "engineering": "8",
    "information technology": "13",
    "it": "13",
    "finance": "10",
    "healthcare services": "11",
    "healthcare": "11",
    "sales": "25",
    "marketing": "15",
    "operations": "18",
    "product": "19",
    "product management": "19",
    "human resources": "12",
    "hr": "12",
}

TITLE_ALIASES = {
    "cio": ("CIO", "Chief Information Officer"),
    "cto": ("CTO", "Chief Technology Officer"),
    "ceo": ("CEO", "Chief Executive Officer"),
    "cfo": ("CFO", "Chief Financial Officer"),
    "coo": ("COO", "Chief Operating Officer"),
    "ciso": ("CISO", "Chief Information Security Officer"),
    "vp engineering": ("VP Engineering", "Vice President of Engineering", "VP of Engineering"),
    "vice president of engineering": ("VP Engineering", "Vice President of Engineering"),
}

LOCATION_EXPANSIONS = {
    "india": ("India",),
    "uae": ("United Arab Emirates",),
    "united arab emirates": ("United Arab Emirates",),
    "southeast asia": ("Singapore", "Indonesia", "Malaysia", "Thailand", "Vietnam"),
    "sea": ("Singapore", "Indonesia", "Malaysia", "Thailand", "Vietnam"),
    "singapore": ("Singapore",),
    "indonesia": ("Indonesia",),
    "malaysia": ("Malaysia",),
    "thailand": ("Thailand",),
    "vietnam": ("Vietnam",),
    "uk": ("United Kingdom",),
    "united kingdom": ("United Kingdom",),
    "usa": ("United States",),
    "us": ("United States",),
    "united states": ("United States",),
}


def _csv(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _headcount(min_employees: int | None, max_employees: int | None) -> tuple[str, ...]:
    if min_employees is None and max_employees is None:
        return ()
    low = min_employees or 1
    high = max_employees or 10_000_000
    return tuple(code for code, start, end in HEADCOUNT if end >= low and start <= high)


def _seniority_ids(labels: list[str]) -> tuple[str, ...]:
    ids: list[str] = []
    for label in labels:
        mapped = SENIORITY_IDS.get(label.lower())
        if mapped and mapped not in ids:
            ids.append(mapped)
    return tuple(ids)


def _industry_ids(labels: list[str]) -> tuple[tuple[str, ...], list[str]]:
    ids: list[str] = []
    unknown: list[str] = []
    for label in labels:
        mapped = INDUSTRY_IDS.get(label.lower())
        if mapped:
            if mapped not in ids:
                ids.append(mapped)
        else:
            unknown.append(label)
    return tuple(ids), unknown


def _function_ids(labels: list[str]) -> tuple[str, ...]:
    ids: list[str] = []
    for label in labels:
        mapped = FUNCTION_IDS.get(label.lower())
        if mapped and mapped not in ids:
            ids.append(mapped)
    return tuple(ids)


def expand_job_titles(labels: list[str]) -> tuple[str, ...]:
    titles: list[str] = []
    for label in labels:
        aliases = TITLE_ALIASES.get(label.lower())
        for title in aliases or (label,):
            if title not in titles:
                titles.append(title)
    return tuple(titles)


def expand_locations(labels: list[str]) -> tuple[str, ...]:
    locations: list[str] = []
    for label in labels:
        expanded = LOCATION_EXPANSIONS.get(label.lower())
        fallback = (label.title() if label == label.lower() else label,)
        for item in expanded or fallback:
            if item not in locations:
                locations.append(item)
    return tuple(locations)


def optional_search_language(*, keywords: str, description: str, leftover_industries: list[str]) -> str:
    parts = [keywords.strip()]
    parts.extend(leftover_industries)
    if description.strip() and not keywords.strip():
        parts.append(description.strip()[:120])
    return ", ".join(part for part in parts if part)


def build_discovery_query(
    icp: ICP | None,
    *,
    search_query: str = "",
    profile_urls: list[str] | None = None,
    max_items: int = 10,
    process_token: str = "",
) -> DiscoveryQuery:
    industries = _csv(icp.industries if icp else "")
    industry_ids, leftover = _industry_ids(industries)
    personas = _csv(icp.personas if icp else "")
    functions = _csv(icp.job_functions if icp else "")
    geos = _csv(icp.geographies if icp else "")
    locations = expand_locations(geos)
    keywords = (icp.keywords if icp else "") or ""
    explicit_search = search_query.strip()
    language = explicit_search or optional_search_language(
        keywords=keywords,
        description=icp.description if icp else "",
        leftover_industries=leftover,
    )
    return DiscoveryQuery(
        industries=", ".join(industries),
        geographies=", ".join(locations or geos),
        search_query=language,
        actor_search_query=explicit_search,
        profile_urls=tuple(url.strip() for url in (profile_urls or []) if url.strip()),
        max_items=max(1, max_items),
        process_token=process_token,
        job_titles=expand_job_titles(personas),
        seniorities=tuple(_csv(icp.seniorities if icp else "")),
        target_companies=tuple(_csv(icp.target_companies if icp else "")),
        keywords=keywords,
        min_employees=icp.min_employees if icp else None,
        max_employees=icp.max_employees if icp else None,
        industry_ids=industry_ids,
        seniority_ids=_seniority_ids(_csv(icp.seniorities if icp else "")),
        company_headcount=_headcount(icp.min_employees if icp else None, icp.max_employees if icp else None),
        function_ids=_function_ids(functions),
        location_names=locations,
    )
