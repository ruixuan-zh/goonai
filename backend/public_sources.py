"""Allow-listed ingestion of non-sensitive Singapore public data.

The collectors preserve every normalised observation locally.  Only compact,
source-linked evidence summaries are passed to the orchestration model.
"""

from __future__ import annotations

import html
import io
import json
import math
import re
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

from .schemas import (
    Domain,
    Evidence,
    Hypothesis,
    PublicDataBundle,
    PublicObservation,
    SourceCoverage,
    SourceStatus,
)


SGT = timezone(timedelta(hours=8))
USER_AGENT = "BIO-SIGNAL-Hackathon/1.0 (public-data research prototype)"
ALLOWED_HOSTS = {
    "www.cda.gov.sg",
    "isomer-user-content.by.gov.sg",
    "www.nea.gov.sg",
    "api-open.data.gov.sg",
    "www.sfa.gov.sg",
    "avs.nparks.gov.sg",
    "www.changiairport.com",
    "www.who.int",
}

CDA_INDEX = "https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-{year}/"
NEA_DENGUE = "https://www.nea.gov.sg/dengue-zika/dengue/dengue-cases"
NEA_CLUSTERS = "https://www.nea.gov.sg/dengue-zika/dengue/dengue-clusters"
NEA_ZIKA = "https://www.nea.gov.sg/dengue-zika/zika/zika-cases-and-clusters"
NEA_WASTEWATER = (
    "https://www.nea.gov.sg/corporate-functions/resources/research/"
    "environmental_health_institute/wastewater-surveillance-programme"
)
SFA_ALERTS = "https://www.sfa.gov.sg/api/ElasticSearch/CircularSearch"
AVS_BIOSURVEILLANCE = (
    "https://avs.nparks.gov.sg/about-us/what-we-do/animal-health/biosurveillance/"
)
CHANGI_TRAFFIC = "https://www.changiairport.com/en/corporate/about-us/traffic-statistics.html"
WHO_DON = (
    "https://www.who.int/api/news/diseaseoutbreaknews?"
    "$top=20&$orderby=PublicationDateAndTime%20desc"
)
ENVIRONMENTAL_ENDPOINTS = {
    "rainfall": "https://api-open.data.gov.sg/v2/real-time/api/rainfall",
    "air_temperature": "https://api-open.data.gov.sg/v2/real-time/api/air-temperature",
    "relative_humidity": "https://api-open.data.gov.sg/v2/real-time/api/relative-humidity",
}


class PublicSourceError(RuntimeError):
    pass


class PublicSourceClient:
    """Small HTTP client that refuses arbitrary or redirected hosts."""

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._ssl_context = ssl.create_default_context()

    @staticmethod
    def _validated_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise PublicSourceError(f"Source URL is not allow-listed: {url}")
        return quote(url, safe=":/?=&%")

    def request_bytes(self, url: str, payload: dict[str, Any] | None = None) -> bytes:
        validated = self._validated_url(url)
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(validated, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context) as response:
                self._validated_url(response.geturl())
                return response.read()
        except Exception as exc:
            raise PublicSourceError(f"Public source request failed: {url}") from exc

    def get_text(self, url: str) -> str:
        return self.request_bytes(url).decode("utf-8", errors="replace")

    def get_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.request_bytes(url))

    def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        return json.loads(self.request_bytes(url, payload))


def _now() -> datetime:
    return datetime.now(SGT)


def _plain_text(markup: str) -> str:
    without_scripts = re.sub(r"<script[\s\S]*?</script>", " ", markup, flags=re.IGNORECASE)
    without_styles = re.sub(r"<style[\s\S]*?</style>", " ", without_scripts, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", without_styles))).strip()


def _coverage(
    source_id: str,
    publisher: str,
    title: str,
    url: str,
    domain: Domain,
    status: SourceStatus,
    count: int,
    cadence: str,
    note: str,
    retrieved_at: datetime,
) -> SourceCoverage:
    return SourceCoverage(
        source_id=source_id,
        publisher=publisher,
        title=title,
        url=url,
        domain=domain,
        status=status,
        retrieved_at=retrieved_at,
        observation_count=count,
        cadence=cadence,
        note=note,
    )


def fetch_cda_bulletin(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    year = retrieved_at.year
    index_url = CDA_INDEX.format(year=year)
    index = client.get_text(index_url)
    links = [
        (int(week), html.unescape(url))
        for url, week in re.findall(
            rf'href="([^"]+\.pdf)"[^>]*>\s*{year}_week_(\d+)', index, flags=re.IGNORECASE
        )
    ]
    if not links:
        raise PublicSourceError("No CDA weekly bulletin PDF was found")
    week, pdf_url = max(links, key=lambda item: item[0])
    reader = PdfReader(io.BytesIO(client.request_bytes(pdf_url)))
    first_page = reader.pages[0].extract_text() or ""
    second_page = reader.pages[1].extract_text() if len(reader.pages) > 1 else ""
    date_match = re.search(
        r"EPIDEMIOLOGICAL WEEK\s+\d+\s+\d+\s*-\s*(\d+)\s+([A-Za-z]+)\s+(\d{4})",
        first_page,
        flags=re.IGNORECASE,
    )
    observed_at = retrieved_at
    if date_match:
        observed_at = datetime.strptime(" ".join(date_match.groups()), "%d %b %Y").replace(tzinfo=SGT)

    observations: list[PublicObservation] = []
    row_pattern = re.compile(
        r"^([A-Za-z][A-Za-z0-9 /&(),.'#^-]*?)\s+((?:\d+|NA)(?:\s+(?:\d+|NA)){2,5})\s*$"
    )
    for line in first_page.splitlines():
        match = row_pattern.match(line.strip())
        if not match:
            continue
        tokens = match.group(2).split()
        if tokens[0] == "NA" or tokens[2] == "NA":
            continue
        name = match.group(1).strip().replace("#", "")
        current = float(tokens[0])
        baseline = float(tokens[2])
        metric = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        observations.append(
            PublicObservation(
                observation_id=f"CDA-EW{week}-{metric}",
                observed_at=observed_at,
                domain=Domain.HUMAN,
                metric=metric,
                value=current,
                unit="weekly notifications" if current < 1000 else "average daily attendances",
                baseline_value=baseline,
                baseline_description="CDA median for the corresponding epidemiological week, 2021-2025",
                source_id="CDA-WEEKLY",
                source_url=pdf_url,
                source_confidence=0.97,
                summary=f"{name}: {current:g} versus a published weekly median of {baseline:g}.",
                limitations="Provisional national aggregate; a deviation does not establish cause or attribution.",
            )
        )

    for metric, pattern in {
        "influenza_ili_positivity": r"positivity rate for influenza[^.]*?was\s+(\d+)%",
        "covid_ari_positivity": r"positivity rate for COVID-19[^.]*?was\s+(\d+)%",
    }.items():
        match = re.search(pattern, second_page or "", flags=re.IGNORECASE)
        if match:
            value = float(match.group(1))
            observations.append(
                PublicObservation(
                    observation_id=f"CDA-EW{week}-{metric}",
                    observed_at=observed_at,
                    domain=Domain.HUMAN,
                    metric=metric,
                    value=value,
                    unit="percent",
                    source_id="CDA-WEEKLY",
                    source_url=pdf_url,
                    source_confidence=0.97,
                    summary=f"{metric.replace('_', ' ').title()}: {value:g}%.",
                    limitations="Sentinel-sample positivity is not population prevalence.",
                )
            )
    return observations, _coverage(
        "CDA-WEEKLY",
        "Communicable Diseases Agency",
        f"Weekly Infectious Diseases Bulletin {year}, epidemiological week {week}",
        pdf_url,
        Domain.HUMAN,
        SourceStatus.AVAILABLE,
        len(observations),
        "Weekly PDF",
        "Notifiable-disease counts, polyclinic attendances and respiratory surveillance.",
        retrieved_at,
    )


def fetch_nea_dengue(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    text = _plain_text(client.get_text(NEA_DENGUE))
    observations: list[PublicObservation] = []
    weekly = re.search(
        r"(\d+) dengue cases were reported in the week ending\s+([^,]+),", text, re.IGNORECASE
    )
    if weekly:
        value = float(weekly.group(1))
        observations.append(
            PublicObservation(
                observation_id=f"NEA-DENGUE-{retrieved_at:%Y%m%d}",
                observed_at=retrieved_at,
                domain=Domain.HUMAN,
                metric="dengue_weekly_cases",
                value=value,
                unit="weekly cases",
                source_id="NEA-DENGUE",
                source_url=NEA_DENGUE,
                source_confidence=0.98,
                summary=f"NEA reports {value:g} dengue cases for the latest completed week.",
                limitations="National reported cases; recent counts may be revised and reflect notification delay.",
            )
        )
    cluster_match = re.search(
        r"(\d+) active\s+dengue clusters were reported, of which\s+([a-z0-9]+) were classified under red",
        text,
        re.IGNORECASE,
    )
    if cluster_match:
        word_numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
        active = int(cluster_match.group(1))
        red_text = cluster_match.group(2).lower()
        red = float(word_numbers.get(red_text, int(red_text) if red_text.isdigit() else 0))
        for suffix, value, summary in (
            ("active-clusters", float(active), f"NEA reports {active} active dengue clusters."),
            ("red-clusters", red, f"NEA reports {red:g} red-alert dengue clusters."),
        ):
            observations.append(
                PublicObservation(
                    observation_id=f"NEA-DENGUE-{retrieved_at:%Y%m%d}-{suffix}",
                    observed_at=retrieved_at,
                    domain=Domain.HUMAN,
                    metric=suffix.replace("-", "_"),
                    value=value,
                    unit="clusters",
                    source_id="NEA-DENGUE",
                    source_url=NEA_DENGUE,
                    source_confidence=0.98,
                    summary=summary,
                    limitations="A cluster is an operational intervention area, not an independent transmission estimate.",
                )
            )
    status = SourceStatus.AVAILABLE if observations else SourceStatus.PARTIAL
    return observations, _coverage(
        "NEA-DENGUE",
        "National Environment Agency",
        "Dengue cases and clusters",
        NEA_DENGUE,
        Domain.HUMAN,
        status,
        len(observations),
        "Daily page; weekly trend preferred",
        "Public case and active-cluster situation for Singapore.",
        retrieved_at,
    )


def fetch_nea_zika(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    text = _plain_text(client.get_text(NEA_ZIKA))
    match = re.search(r"Cumulative No\. of cases for\s+(\d{4}).{0,80}?:\s*(\d+)", text, re.IGNORECASE)
    observations: list[PublicObservation] = []
    if match:
        observations.append(
            PublicObservation(
                observation_id=f"NEA-ZIKA-{match.group(1)}",
                observed_at=retrieved_at,
                domain=Domain.HUMAN,
                metric="zika_cumulative_cases",
                value=float(match.group(2)),
                unit="year-to-date cases",
                source_id="NEA-ZIKA",
                source_url=NEA_ZIKA,
                source_confidence=0.98,
                summary=f"NEA reports {match.group(2)} cumulative Zika cases in {match.group(1)}.",
                limitations="Cumulative national total is not a current incidence rate.",
            )
        )
    return observations, _coverage(
        "NEA-ZIKA",
        "National Environment Agency",
        "Zika cases and clusters",
        NEA_ZIKA,
        Domain.HUMAN,
        SourceStatus.AVAILABLE if observations else SourceStatus.PARTIAL,
        len(observations),
        "Daily page",
        "Public Zika case and cluster situation.",
        retrieved_at,
    )


def fetch_environment(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    observations: list[PublicObservation] = []
    units = {"rainfall": "mm/5 min", "air_temperature": "°C", "relative_humidity": "%"}
    for metric, url in ENVIRONMENTAL_ENDPOINTS.items():
        payload = client.get_json(url)
        readings = payload.get("data", {}).get("readings", [])
        if not readings:
            continue
        latest = readings[0]
        values = [float(item["value"]) for item in latest.get("data", []) if item.get("value") is not None]
        if not values:
            continue
        observed_at = datetime.fromisoformat(latest["timestamp"])
        for statistic, value in (("mean", mean(values)), ("minimum", min(values)), ("maximum", max(values))):
            observations.append(
                PublicObservation(
                    observation_id=f"DATA-GOV-{metric}-{statistic}-{observed_at:%Y%m%dT%H%M}",
                    observed_at=observed_at,
                    domain=Domain.ENVIRONMENTAL,
                    metric=f"{metric}_{statistic}",
                    value=round(value, 3),
                    unit=units[metric],
                    source_id="DATA-GOV-WEATHER",
                    source_url=url,
                    source_confidence=0.96,
                    summary=f"Singapore station {statistic} {metric.replace('_', ' ')}: {value:.2f} {units[metric]}.",
                    limitations="A current station snapshot is contextual and is not, by itself, a disease predictor.",
                )
            )
    return observations, _coverage(
        "DATA-GOV-WEATHER",
        "data.gov.sg / National Environment Agency",
        "Real-time rainfall, temperature and humidity",
        ENVIRONMENTAL_ENDPOINTS["rainfall"],
        Domain.ENVIRONMENTAL,
        SourceStatus.AVAILABLE if observations else SourceStatus.PARTIAL,
        len(observations),
        "Near-real-time JSON API",
        "Current station summaries; historical lag features require a stored time series.",
        retrieved_at,
    )


def _sfa_payload() -> dict[str, Any]:
    raw = {"raw": {}}
    return {
        "query": "",
        "search_fields": {"title": {"weight": 100}},
        "result_fields": {
            "id": raw,
            "title": raw,
            "date_of_publication_local": raw,
            "url": raw,
        },
        "filters": {
            "all": [
                {"master_type": ["page", "document"]},
                {"content_types": "food-alerts-recalls"},
            ],
            "none": [],
        },
        "page": {"size": 20, "current": 1},
        "precision": 8,
        "sort": {"date_of_publication_local": "desc"},
    }


def fetch_sfa_alerts(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    payload = client.post_json(SFA_ALERTS, _sfa_payload())
    observations: list[PublicObservation] = []
    for item in payload.get("results", []):
        title = item.get("title", {}).get("raw")
        published = item.get("date_of_publication_local", {}).get("raw")
        source_url = item.get("url", {}).get("raw")
        record_id = item.get("id", {}).get("raw")
        if not all((title, published, source_url, record_id)):
            continue
        published_at = datetime.fromisoformat(published)
        observations.append(
            PublicObservation(
                observation_id=f"SFA-{record_id}",
                observed_at=published_at,
                domain=Domain.FOOD,
                metric="food_alert_or_recall",
                value=1,
                unit="published alert",
                source_id="SFA-ALERTS",
                source_url=source_url,
                source_confidence=0.96,
                summary=title,
                limitations="A recall may be precautionary and does not imply a Singapore outbreak.",
            )
        )
    return observations, _coverage(
        "SFA-ALERTS",
        "Singapore Food Agency",
        "Food alerts and recalls",
        "https://www.sfa.gov.sg/news-publications/circulars-and-notices/food-alerts-and-recalls",
        Domain.FOOD,
        SourceStatus.AVAILABLE if observations else SourceStatus.PARTIAL,
        len(observations),
        "Event-driven structured search endpoint",
        "Latest public food-safety notices; each notice retains its source URL.",
        retrieved_at,
    )


def fetch_changi_mobility(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    text = _plain_text(client.get_text(CHANGI_TRAFFIC))
    match = re.search(r"([A-Za-z]+)\s+(\d{4}):\s*([\d.]+)m passenger movements", text)
    observations: list[PublicObservation] = []
    if match:
        observed_at = datetime.strptime(f"1 {match.group(1)} {match.group(2)}", "%d %B %Y").replace(tzinfo=SGT)
        value = float(match.group(3)) * 1_000_000
        observations.append(
            PublicObservation(
                observation_id=f"CHANGI-PAX-{observed_at:%Y%m}",
                observed_at=observed_at,
                domain=Domain.MOBILITY,
                metric="monthly_passenger_movements",
                value=value,
                unit="passenger movements",
                source_id="CHANGI-TRAFFIC",
                source_url=CHANGI_TRAFFIC,
                source_confidence=0.94,
                summary=f"Changi reports {match.group(3)} million passenger movements in {match.group(1)} {match.group(2)}.",
                limitations="Monthly passenger volume is a lagged exposure proxy, not evidence of disease importation.",
            )
        )
    return observations, _coverage(
        "CHANGI-TRAFFIC",
        "Changi Airport Group",
        "Air traffic statistics",
        CHANGI_TRAFFIC,
        Domain.MOBILITY,
        SourceStatus.AVAILABLE if observations else SourceStatus.PARTIAL,
        len(observations),
        "Monthly HTML statistics",
        "Passenger movements provide import-exposure context only.",
        retrieved_at,
    )


def fetch_who_outbreak_news(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    """Collect bounded international outbreak context that may affect Singapore import risk."""

    retrieved_at = _now()
    payload = client.get_json(WHO_DON)
    regional_terms = {
        "singapore",
        "malaysia",
        "indonesia",
        "thailand",
        "vietnam",
        "philippines",
        "cambodia",
        "lao",
        "myanmar",
        "brunei",
        "china",
        "hong kong",
        "taiwan",
        "india",
        "bangladesh",
        "south asia",
        "south-east asia",
        "southeast asia",
        "western pacific",
    }
    observations: list[PublicObservation] = []
    for item in payload.get("value", [])[:20]:
        title = item.get("Title") or item.get("OverrideTitle")
        published = item.get("PublicationDateAndTime") or item.get("PublicationDate")
        url_name = item.get("UrlName")
        if not all((title, published, url_name)):
            continue
        overview = _plain_text(item.get("Overview") or "")
        combined = f"{title} {overview}".lower()
        is_regional = any(term in combined for term in regional_terms)
        source_url = f"https://www.who.int/emergencies/disease-outbreak-news/item/{url_name}"
        observations.append(
            PublicObservation(
                observation_id=f"WHO-DON-{item.get('DonId') or item.get('Id')}",
                observed_at=datetime.fromisoformat(published.replace("Z", "+00:00")),
                domain=Domain.EXTERNAL,
                metric="regional_outbreak_report" if is_regional else "global_outbreak_report",
                value=1,
                unit="official outbreak report",
                geography_scope="Regional relevance to Singapore" if is_regional else "Global context",
                source_id="WHO-DON",
                source_url=source_url,
                source_confidence=0.96,
                summary=title,
                limitations="A foreign outbreak report is contextual evidence, not proof of importation into Singapore.",
            )
        )
    return observations, _coverage(
        "WHO-DON",
        "World Health Organization",
        "Disease Outbreak News",
        "https://www.who.int/emergencies/disease-outbreak-news",
        Domain.EXTERNAL,
        SourceStatus.AVAILABLE if observations else SourceStatus.PARTIAL,
        len(observations),
        "Event-driven official JSON API",
        "Latest twenty WHO reports; regional relevance is screened locally for Singapore import-risk context.",
        retrieved_at,
    )


def fetch_avs_coverage(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    text = _plain_text(client.get_text(AVS_BIOSURVEILLANCE))
    confirmed = "regular animal health monitoring surveys" in text.lower()
    return [], _coverage(
        "AVS-BIOSURVEILLANCE",
        "Animal and Veterinary Service, NParks",
        "Animal-health biosurveillance",
        AVS_BIOSURVEILLANCE,
        Domain.ANIMAL,
        SourceStatus.CONTEXT_ONLY if confirmed else SourceStatus.PARTIAL,
        0,
        "Programme description and public advisories",
        "AVS confirms monitoring of birds, wild mammals and food animals, but no granular public time series was found.",
        retrieved_at,
    )


def fetch_wastewater_coverage(client: PublicSourceClient) -> tuple[list[PublicObservation], SourceCoverage]:
    retrieved_at = _now()
    text = _plain_text(client.get_text(NEA_WASTEWATER))
    confirmed = "more than 500 sites" in text.lower()
    return [], _coverage(
        "NEA-WASTEWATER",
        "National Environment Agency / CDA / PUB",
        "Wastewater Surveillance Programme",
        NEA_WASTEWATER,
        Domain.ENVIRONMENTAL,
        SourceStatus.CONTEXT_ONLY if confirmed else SourceStatus.PARTIAL,
        0,
        "Programme description",
        "The public page confirms national coverage, but does not expose current site-level viral measurements.",
        retrieved_at,
    )


def collect_singapore_public_data(client: PublicSourceClient | None = None) -> PublicDataBundle:
    """Collect all supported sources; one source failure never hides the others."""

    client = client or PublicSourceClient()
    collectors = {
        "CDA-WEEKLY": fetch_cda_bulletin,
        "NEA-DENGUE": fetch_nea_dengue,
        "NEA-ZIKA": fetch_nea_zika,
        "DATA-GOV-WEATHER": fetch_environment,
        "SFA-ALERTS": fetch_sfa_alerts,
        "CHANGI-TRAFFIC": fetch_changi_mobility,
        "WHO-DON": fetch_who_outbreak_news,
        "AVS-BIOSURVEILLANCE": fetch_avs_coverage,
        "NEA-WASTEWATER": fetch_wastewater_coverage,
    }
    observations: list[PublicObservation] = []
    sources: list[SourceCoverage] = []
    retrieved_at = _now()
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(collector, client): source_id for source_id, collector in collectors.items()}
        for future in as_completed(futures):
            source_id = futures[future]
            try:
                source_observations, coverage = future.result()
                observations.extend(source_observations)
                sources.append(coverage)
            except Exception as exc:
                sources.append(
                    _coverage(
                        source_id,
                        source_id,
                        "Public source",
                        "",
                        Domain.EXTERNAL,
                        SourceStatus.UNAVAILABLE,
                        0,
                        "Unknown",
                        f"Collection failed safely: {type(exc).__name__}",
                        retrieved_at,
                    )
                )
    return PublicDataBundle(
        retrieved_at=retrieved_at,
        observations=sorted(observations, key=lambda item: (item.domain.value, item.metric)),
        sources=sorted(sources, key=lambda item: item.source_id),
    )


def public_bundle_to_evidence(bundle: PublicDataBundle) -> list[Evidence]:
    """Compress all observations into a few bounded, provenance-linked evidence items."""

    evidence: list[Evidence] = []
    by_source: dict[str, list[PublicObservation]] = {}
    for observation in bundle.observations:
        by_source.setdefault(observation.source_id, []).append(observation)

    cda = by_source.get("CDA-WEEKLY", [])
    comparable = [item for item in cda if item.baseline_value is not None]
    unusual = [
        item
        for item in comparable
        if item.value - (item.baseline_value or 0)
        >= max(2.0, 1.5 * math.sqrt(max(item.baseline_value or 0, 1.0)))
    ]
    unusual.sort(
        key=lambda item: (item.value - (item.baseline_value or 0))
        / math.sqrt(max(item.baseline_value or 0, 1.0)),
        reverse=True,
    )
    if cda:
        finding = (
            "CDA weekly screening found these largest deviations from its published weekly median: "
            + "; ".join(item.summary for item in unusual[:5])
            if unusual
            else "CDA weekly screening found no large count deviation under the prototype rule."
        )
        evidence.append(
            Evidence(
                evidence_id="EV-PUBLIC-CDA-WEEKLY",
                finding=finding,
                source_ids=["CDA-WEEKLY"],
                quality=0.97,
                hypothesis_effects={
                    Hypothesis.NATURAL_ZOONOTIC: min(14.0, 3.0 * len(unusual)),
                    Hypothesis.ACCIDENTAL_RELEASE: 0.0,
                    Hypothesis.DELIBERATE_RELEASE: 0.0,
                    Hypothesis.INSUFFICIENT_EVIDENCE: -min(5.0, float(len(unusual))),
                },
                limitations="The rule is a transparent screening heuristic; public aggregates cannot determine attribution.",
            )
        )

    for source_id, evidence_id, effects in (
        (
            "NEA-DENGUE",
            "EV-PUBLIC-NEA-DENGUE",
            {Hypothesis.NATURAL_ZOONOTIC: 3.0, Hypothesis.INSUFFICIENT_EVIDENCE: 0.0},
        ),
        (
            "NEA-ZIKA",
            "EV-PUBLIC-NEA-ZIKA",
            {Hypothesis.NATURAL_ZOONOTIC: 2.0, Hypothesis.INSUFFICIENT_EVIDENCE: 0.0},
        ),
        (
            "DATA-GOV-WEATHER",
            "EV-PUBLIC-ENVIRONMENT",
            {Hypothesis.NATURAL_ZOONOTIC: 1.0, Hypothesis.INSUFFICIENT_EVIDENCE: 1.0},
        ),
        (
            "CHANGI-TRAFFIC",
            "EV-PUBLIC-MOBILITY",
            {Hypothesis.NATURAL_ZOONOTIC: 1.0, Hypothesis.INSUFFICIENT_EVIDENCE: 1.0},
        ),
    ):
        items = by_source.get(source_id, [])
        if items:
            full_effects = {hypothesis: 0.0 for hypothesis in Hypothesis}
            full_effects.update(effects)
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    finding=" ".join(item.summary for item in items[:6]),
                    source_ids=[source_id],
                    quality=min(item.source_confidence for item in items),
                    hypothesis_effects=full_effects,
                    limitations=" ".join(dict.fromkeys(item.limitations for item in items)),
                )
            )

    sfa = by_source.get("SFA-ALERTS", [])
    recent_sfa = [item for item in sfa if bundle.retrieved_at - item.observed_at <= timedelta(days=90)]
    if sfa:
        evidence.append(
            Evidence(
                evidence_id="EV-PUBLIC-SFA-ALERTS",
                finding=(
                    f"SFA published {len(recent_sfa)} food alert(s) in the preceding 90 days. "
                    + " | ".join(item.summary for item in recent_sfa[:3])
                ).strip(),
                source_ids=["SFA-ALERTS"],
                quality=0.96,
                hypothesis_effects={
                    Hypothesis.NATURAL_ZOONOTIC: min(4.0, float(len(recent_sfa))),
                    Hypothesis.ACCIDENTAL_RELEASE: 1.0 if recent_sfa else 0.0,
                    Hypothesis.DELIBERATE_RELEASE: 0.0,
                    Hypothesis.INSUFFICIENT_EVIDENCE: 1.0,
                },
                limitations="Food recalls are heterogeneous and do not imply a linked human outbreak.",
            )
        )

    who = by_source.get("WHO-DON", [])
    regional_who = [item for item in who if item.metric == "regional_outbreak_report"]
    recent_who = [item for item in regional_who if bundle.retrieved_at - item.observed_at <= timedelta(days=90)]
    if who:
        selected = recent_who[:5] or who[:3]
        evidence.append(
            Evidence(
                evidence_id="EV-PUBLIC-WHO-DON",
                finding=(
                    f"WHO Disease Outbreak News returned {len(recent_who)} recent regional report(s) "
                    "screened as potentially relevant to Singapore. "
                    + " | ".join(item.summary for item in selected)
                ),
                source_ids=["WHO-DON"],
                quality=0.96,
                hypothesis_effects={
                    Hypothesis.NATURAL_ZOONOTIC: min(4.0, float(len(recent_who))),
                    Hypothesis.ACCIDENTAL_RELEASE: 0.0,
                    Hypothesis.DELIBERATE_RELEASE: 0.0,
                    Hypothesis.INSUFFICIENT_EVIDENCE: 1.0,
                },
                limitations="Regional relevance is keyword-screened; importation and linkage require Singapore evidence.",
            )
        )

    critical_gaps = [
        source
        for source in bundle.sources
        if source.source_id in {"AVS-BIOSURVEILLANCE", "NEA-WASTEWATER"}
        and source.observation_count == 0
    ]
    if critical_gaps:
        evidence.append(
            Evidence(
                evidence_id="EV-PUBLIC-COVERAGE-GAPS",
                finding=(
                    "Public-source coverage gap: current granular animal-health and wastewater measurements "
                    "are not exposed by the verified programme pages."
                ),
                source_ids=[source.source_id for source in critical_gaps],
                quality=0.98,
                hypothesis_effects={
                    Hypothesis.NATURAL_ZOONOTIC: -5.0,
                    Hypothesis.ACCIDENTAL_RELEASE: -2.0,
                    Hypothesis.DELIBERATE_RELEASE: -2.0,
                    Hypothesis.INSUFFICIENT_EVIDENCE: 20.0,
                },
                limitations="An unavailable public feed does not mean the underlying surveillance programme lacks data.",
            )
        )
    return evidence
