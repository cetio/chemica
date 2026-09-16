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
from dataclasses import replace

import requests

from chemica import cache
from chemica.core import (
    Article,
    Classifications,
    Compound,
    DoseLadder,
    EffectGroup,
    EffectsProfile,
    Interaction,
    SubjectiveProfile,
)
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
# Inline HTML (<span style=...> wrappers in duration fields) and bold/italic
# apostrophe runs (''...''', '''...''') — both leaked into Gantt labels raw.
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_APOSTROPHE_RE = re.compile(r"'{2,}")
# A truncated {{template dangling at the end of a value — PW fields are
# single-line, so an unclosed opener means the tail is markup (the
# bioavailability cite-journal leak c fixed display-side). Open <ref>
# tags are already stripped by _TAG_RE.
_UNTERMINATED_RE = re.compile(r"\{\{[^{}]*$")

# [[SeverityInteraction::Substance]] — PW's semantic annotations in the
# 'Dangerous interactions' section; severity is the tag prefix.
_INTERACTION_RE = re.compile(r"\[\[(Dangerous|Unsafe|Uncertain)Interaction::([^\]]+)\]\]")
_INTERACTIONS_SECTION_RE = re.compile(
    r"={2,4}\s*Dangerous interactions\s*={2,4}(.*?)(?=\n={2,4}|\Z)",
    re.IGNORECASE | re.DOTALL,
)
# [[Chemical class::arylcyclohexylamine]] / [[Psychoactive class::dissociative]]
# — semantic annotations in the lead prose, same :: pattern as interactions.
_CLASS_RE = re.compile(r"\[\[(Chemical|Psychoactive) class::([^\]]+)\]\]", re.IGNORECASE)
# [[Addiction potential::…]], [[Time to X tolerance::…]], [[Effect::X]] —
# same semantic-annotation family, safety/subjective rather than taxonomy.
_EFFECT_RE = re.compile(r"\[\[(?:E|e)ffect::([^\]]+)\]\]")
_ADDICTION_RE = re.compile(r"\[\[Addiction potential::([^\]]+)\]\]")
_TOLERANCE_RE = re.compile(r"\[\[Time to (full|half|zero) tolerance::([^\]]+)\]\]")

# SubstanceBox wikitext by page title — stable per session, process-lifetime.
_BOX_CACHE: dict[str, str | None] = {}
_PAGE_WT_CACHE: dict[str, str | None] = {}

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

    def fetch_interactions(self, query: str) -> list[Interaction]:
        """Dangerous/unsafe/uncertain interactions from the article wikitext."""
        wikitext = self._page_wikitext(query)
        return _interactions(wikitext) if wikitext else []

    def fetch_classes(self, query: str) -> Classifications | None:
        """Chemical/psychoactive class annotations from the lead wikitext —
        shares the same page fetch the interactions parser already made."""
        wikitext = self._page_wikitext(query)
        if not wikitext:
            return None
        fields: dict[str, str] = {}
        for kind, value in _CLASS_RE.findall(wikitext):
            fields.setdefault(kind.lower(), value.strip())
        if not fields:
            return None
        return Classifications(
            chemical=fields.get("chemical"),
            psychoactive=fields.get("psychoactive"),
        )

    def fetch_subjective(self, query: str) -> SubjectiveProfile | None:
        """Addiction potential, tolerance timelines, and effect tags — the
        same memoized page wikitext, one more regex family."""
        wikitext = self._page_wikitext(query)
        if not wikitext:
            return None
        groups = _effect_groups(wikitext)
        profile = SubjectiveProfile(
            addiction_potential=_first(_ADDICTION_RE, wikitext),
            effect_tags=list(dict.fromkeys(tag for group in groups for tag in group.effects)),
            effect_groups=groups,
        )
        for span, value in _TOLERANCE_RE.findall(wikitext):
            field_name = "tolerance_" + span.lower()
            profile = replace(profile, **{field_name: value.strip()})
        return profile if profile != SubjectiveProfile() else None

    def _page_wikitext(self, query: str) -> str | None:
        title = mediawiki.resolve_title(API, query)
        if title is None:
            return None
        if title not in _PAGE_WT_CACHE:
            wikitext = self._fetch_wikitext(title)
            if wikitext:
                _PAGE_WT_CACHE[title] = wikitext
            return wikitext
        return _PAGE_WT_CACHE[title]

    def _substancebox(self, title: str) -> str | None:
        if title not in _BOX_CACHE:
            wikitext = self._fetch_wikitext(f"Template:SubstanceBox/{title}")
            if wikitext:
                _BOX_CACHE[title] = wikitext
            return wikitext
        return _BOX_CACHE[title]

    def _fetch_wikitext(self, page: str) -> str | None:
        url = f"{API}?action=parse&prop=wikitext&format=json&formatversion=2&page={requests.utils.quote(page)}"
        resp = cache.get(url, timeout=15, headers=mediawiki.HEADERS)
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


# Stop at the next level-2 heading — ==== subheads inside the section are
# the effect groups themselves, not the end of it.
_SUBJECTIVE_SECTION_RE = re.compile(
    r"={2}\s*Subjective effects\s*={2}(.*?)(?=\n==[^=]|\Z)",
    re.IGNORECASE | re.DOTALL,
)
# {{effects/physical|…}} opens a group; ====Subhead==== splits it further.
_EFFECT_TEMPLATE_RE = re.compile(r"\{\{effects/(\w+)", re.IGNORECASE)
_SUBHEAD_RE = re.compile(r"={3,4}\s*([^=]+?)\s*={3,4}")


def _effect_groups(wikitext: str) -> list[EffectGroup]:
    section = _SUBJECTIVE_SECTION_RE.search(wikitext)
    if section is None:
        return []
    groups: list[EffectGroup] = []
    label: str | None = None
    for line in section.group(1).splitlines():
        template = _EFFECT_TEMPLATE_RE.search(line)
        subhead = _SUBHEAD_RE.match(line.strip())
        if template:
            label = template.group(1).capitalize()
        elif subhead:
            label = subhead.group(1).strip()
        tags = [m.group(1).split("|")[-1].strip() for m in _EFFECT_RE.finditer(line)]
        if tags:
            if not groups or groups[-1].label != label:
                groups.append(EffectGroup(label=label))
            groups[-1].effects.extend(tags)
    return groups


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def _interactions(wikitext: str) -> list[Interaction]:
    section = _INTERACTIONS_SECTION_RE.search(wikitext)
    if section is None:
        return []
    ret: list[Interaction] = []
    for line in section.group(1).splitlines():
        line = line.strip().lstrip("*")
        refs = _INTERACTION_RE.findall(line)
        if not refs:
            continue
        # Everything after ' - ' describes the whole line; several
        # substances on one bullet share it (e.g. GHB / GBL).
        desc = line.split(" - ", 1)[1] if " - " in line else ""
        desc = _clean_value(desc) or None
        for severity, substance in refs:
            ret.append(
                Interaction(
                    substance=substance.strip(),
                    severity=severity.lower(),
                    description=desc,
                )
            )
    return ret


def _clean_value(raw: str) -> str:
    value = _SEM_RE.sub(lambda m: m.group(1).strip(), raw)
    value = _LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), value)
    value = _REF_RE.sub("", value)
    value = _COMMENT_RE.sub("", value)
    value = _TAG_RE.sub(" ", value)
    value = _APOSTROPHE_RE.sub("", value)
    value = _TEMPLATE_RE.sub("", value)
    value = _UNTERMINATED_RE.sub("", value)
    return value.strip()
