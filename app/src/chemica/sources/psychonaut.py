"""PsychonautWiki source — substance article plus dosage/duration profile.

PsychonautWiki runs MediaWiki with the TextExtracts extension, so article
fetching is the same resolve-then-extract as Wikipedia against
psychonautwiki.org. The dosage data lives in Template:SubstanceBox/{title}
wikitext as |{Route}ROA_{Field} entries — the same shape the D app's
akashi.psychonaut parsed.

Coverage is recreational substances only — common pharmaceuticals like aspirin
have no page, in which case every method declines (returns None/empty) and the
blend moves on.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the
pytest suite so CI never depends on network reachability.
"""

from __future__ import annotations

import re

import requests

from chemica.core import Article, Compound, DoseLadder, EffectsProfile
from chemica.sources import mediawiki

API = "https://psychonautwiki.org/w/api.php"
SITE = "https://psychonautwiki.org/wiki"

# |OralROA=true marks an active route; |OralROA_{Field}=... carries the data.
# The gap around = is [ \t]*, not \s* — an empty field like |OralROA_Caption=
# would otherwise let \s* eat the newline and swallow the next line as its value.
_ROUTE_FLAG_RE = re.compile(r"\|\s*(\w+)ROA[ \t]*=[ \t]*true", re.IGNORECASE)
_ROUTE_FIELD_RE = re.compile(r"\|\s*(\w+)ROA_(\w+)[ \t]*=[ \t]*([^\n]+)")

# Wikitext cleanup, ported from akashi.psychonaut's cleanValue:
# [[prop::value]] semantic annotations keep the value, [[a|b]] keeps b,
# [[a]] keeps a, <ref> tags and {{ templates are stripped.
_SEM_RE = re.compile(r"\[\[[^\]]*::([^\]]*)\]\]")
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL)
_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# SubstanceBox wikitext by page title — stable per session, process-lifetime.
_BOX_CACHE: dict[str, str | None] = {}

_DOSE_FIELDS = {"Threshold", "Light", "Common", "Strong", "Heavy", "Bioavailability"}
_TIME_FIELDS = {"Duration", "Onset", "Comeup", "Peak", "Offset", "Aftereffects"}


class PsychonautWikiSource:
    name = "psychonautwiki"

    def fetch_article(self, query: str) -> Article | None:
        title = mediawiki.resolve_title(API, query)
        if title is None:
            return None
        sections = mediawiki.extract_sections(API, title)
        if not sections:
            return None
        return Article(
            title=title,
            sections=sections,
            url=f"{SITE}/{requests.utils.quote(title)}",
            source="psychonautwiki",
            raw={"title": title},
        )

    def fetch_profile(self, query: str) -> tuple[list[DoseLadder], list[EffectsProfile]]:
        """Dose ladders + timelines per route from the SubstanceBox template."""
        title = mediawiki.resolve_title(API, query)
        if title is None:
            return [], []
        wikitext = self._substancebox(title)
        if not wikitext:
            return [], []
        return _dose_ladders(wikitext), _effects_profiles(wikitext)

    def fetch_compound(self, query: str) -> Compound | None:
        return None

    def _substancebox(self, title: str) -> str | None:
        if title not in _BOX_CACHE:
            _BOX_CACHE[title] = self._fetch_substancebox(title)
        return _BOX_CACHE[title]

    def _fetch_substancebox(self, title: str) -> str | None:
        url = (
            f"{API}?action=parse&prop=wikitext&format=json&formatversion=2"
            f"&page={requests.utils.quote('Template:SubstanceBox/' + title)}"
        )
        resp = requests.get(url, timeout=15, headers=mediawiki.HEADERS)
        if resp.status_code != 200:
            return None
        wikitext = resp.json().get("parse", {}).get("wikitext")
        return wikitext if isinstance(wikitext, str) else None


def _route_fields(wikitext: str) -> dict[str, dict[str, str]]:
    """Collect |{Route}ROA_{Field} values for routes flagged active."""
    active = {m.group(1) for m in _ROUTE_FLAG_RE.finditer(wikitext)}
    routes: dict[str, dict[str, str]] = {}
    for m in _ROUTE_FIELD_RE.finditer(wikitext):
        route, field_name, raw = m.group(1), m.group(2), m.group(3)
        if route not in active:
            continue
        value = _clean_value(raw)
        # The D code skipped multi-part doses like "500 mg x 2" — keep that.
        if value and " x " not in value:
            routes.setdefault(route, {})[field_name] = value
    return routes


def _dose_ladders(wikitext: str) -> list[DoseLadder]:
    ladders: list[DoseLadder] = []
    for route, fields in _route_fields(wikitext).items():
        if not fields.keys() & _DOSE_FIELDS:
            continue
        ladders.append(
            DoseLadder(
                route=route,
                threshold=fields.get("Threshold"),
                light=fields.get("Light"),
                common=fields.get("Common"),
                strong=fields.get("Strong"),
                heavy=fields.get("Heavy"),
                bioavailability=fields.get("Bioavailability"),
            )
        )
    return ladders


def _effects_profiles(wikitext: str) -> list[EffectsProfile]:
    profiles: list[EffectsProfile] = []
    for route, fields in _route_fields(wikitext).items():
        if not fields.keys() & _TIME_FIELDS:
            continue
        profiles.append(
            EffectsProfile(
                route=route,
                onset=fields.get("Onset"),
                comeup=fields.get("Comeup"),
                peak=fields.get("Peak"),
                offset=fields.get("Offset"),
                total=fields.get("Duration"),
                aftereffects=fields.get("Aftereffects"),
            )
        )
    return profiles


def _clean_value(raw: str) -> str:
    value = _SEM_RE.sub(lambda m: m.group(1).strip(), raw)
    value = _LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), value)
    value = _REF_RE.sub("", value)
    value = _TEMPLATE_RE.sub("", value)
    value = _COMMENT_RE.sub("", value)
    return value.strip()
