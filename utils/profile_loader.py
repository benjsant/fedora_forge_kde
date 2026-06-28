#!/usr/bin/env python3
"""
FedoraForgeKDE - Profile Loader
-----------------------------
Load and validate installation profiles from configs/profiles/.
"""

import json
from pathlib import Path

from schemas.profile import Profile

PROFILES_DIR = Path(__file__).parent.parent / "configs" / "profiles"


def load_profile(filepath: Path) -> Profile:
    """Load and validate a single profile JSON file."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    return Profile(**data)


def load_all_profiles() -> dict[str, Profile]:
    """Load all profiles from configs/profiles/."""
    profiles: dict[str, Profile] = {}
    if not PROFILES_DIR.is_dir():
        return profiles

    for path in sorted(PROFILES_DIR.glob("*.json")):
        slug = path.stem
        try:
            profiles[slug] = load_profile(path)
        except Exception as e:
            from .logging_utils import warn
            warn(f"Profile '{slug}' invalide, ignore: {e}")

    return profiles


def get_profile(slug: str) -> Profile | None:
    """Load a single profile by slug name."""
    path = PROFILES_DIR / f"{slug}.json"
    if not path.exists():
        return None
    return load_profile(path)


def list_profile_slugs() -> list[str]:
    """Return available profile slug names."""
    if not PROFILES_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))
