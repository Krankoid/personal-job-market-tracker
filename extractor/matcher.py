"""
Keyword-based skill extractor.

Loads skills.yaml once at import time, compiles regex patterns, and exposes
extract_skills(text) -> list[dict].

Special handling:
- Aliases starting with \\b are used as raw regex (for single-letter / acronym skills).
- The skill "R" is matched case-sensitively to avoid matching "r" inside Danish words.
"""
import re
from pathlib import Path
from typing import NamedTuple

import yaml

import config

# Skills whose matching must be case-sensitive (applied before lowercasing text).
_CASE_SENSITIVE_SKILLS = {"R"}


class _SkillEntry(NamedTuple):
    name: str
    category: str
    patterns: list  # list of compiled re.Pattern


def _build_pattern(alias: str, case_sensitive: bool) -> re.Pattern:
    """Compile a single alias string into a regex pattern."""
    flags = 0 if case_sensitive else re.IGNORECASE
    if alias.startswith("\\b"):
        # Raw regex provided by the taxonomy author
        return re.compile(alias, flags)
    return re.compile(r"\b" + re.escape(alias) + r"\b", flags)


def _load_taxonomy() -> list[_SkillEntry]:
    with open(config.SKILLS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries: list[_SkillEntry] = []
    for category, skills in data["categories"].items():
        for skill in skills:
            name = skill["name"]
            case_sensitive = name in _CASE_SENSITIVE_SKILLS
            patterns = [_build_pattern(alias, case_sensitive) for alias in skill["aliases"]]
            entries.append(_SkillEntry(name=name, category=category, patterns=patterns))
    return entries


# Compiled once at import time — shared across all calls.
_TAXONOMY: list[_SkillEntry] = _load_taxonomy()


def _normalize(text: str) -> str:
    """Lowercase and strip punctuation, preserving '+' for 'C++'."""
    text = text.lower()
    # Replace all punctuation except '+' and word-boundary-relevant chars with space
    text = re.sub(r"[^\w\s+]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_skills(text: str) -> list[dict]:
    """
    Match skills against raw job description text.

    Returns a list of dicts sorted by match count (descending):
      [{"skill": str, "category": str, "count": int}, ...]
    """
    if not text:
        return []

    normalized = _normalize(text)

    results = []
    for entry in _TAXONOMY:
        if entry.name in _CASE_SENSITIVE_SKILLS:
            # Match against the original (non-lowercased) text for case-sensitive skills
            search_text = text
        else:
            search_text = normalized

        total = sum(len(p.findall(search_text)) for p in entry.patterns)
        if total > 0:
            results.append({"skill": entry.name, "category": entry.category, "count": total})

    results.sort(key=lambda x: x["count"], reverse=True)
    return results
