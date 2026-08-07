from __future__ import annotations

from ..config import DigestConfig
from ..models import ParsedBundle
from .base import PaperProfile, ProfileScore
from .universal import UniversalProfile


def available_profiles(config: DigestConfig, repair_pass: int = 0) -> list[PaperProfile]:
    return [UniversalProfile(config, repair_pass)]


def choose_profile(
    bundle: ParsedBundle,
    requested: str = "auto",
    *,
    config: DigestConfig | None = None,
    repair_pass: int = 0,
) -> tuple[PaperProfile, list[ProfileScore]]:
    config = config or DigestConfig()
    profiles = available_profiles(config, repair_pass)
    if requested not in {"auto", "universal", "generic"}:
        raise ValueError(f"Unknown profile: {requested}")
    profile = profiles[0]
    profile.classify(bundle)
    scores = [profile.score(bundle)]
    return profile, scores
