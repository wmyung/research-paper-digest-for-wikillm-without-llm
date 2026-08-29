"""Study-design vocabulary for the `category` frontmatter slug.

Scoring is a weighted count of fixed terms over the title, abstract and body.
Terms are weighted because a design word in the title is far more diagnostic
than the same word buried in a discussion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text import normalize_prose


@dataclass(frozen=True, slots=True)
class Design:
    category: str
    research_fields: tuple[str, ...]
    terms: tuple[str, ...]
    strong_terms: tuple[str, ...] = ()


DESIGNS: tuple[Design, ...] = (
    Design(
        "randomized-trial",
        ("clinical research", "randomized trials"),
        ("randomised", "randomized", "placebo", "allocation concealment", "intention to treat", "trial registration"),
        ("randomised controlled trial", "randomized controlled trial", "rct"),
    ),
    Design(
        "meta-analysis",
        ("evidence synthesis", "meta-analysis"),
        ("pooled effect", "heterogeneity", "forest plot", "random-effects model", "i2 statistic"),
        ("meta-analysis", "meta-analyses"),
    ),
    Design(
        "systematic-review",
        ("evidence synthesis", "systematic review"),
        ("search strategy", "prisma", "eligibility criteria", "risk of bias", "screening of records"),
        ("systematic review", "scoping review", "rapid review"),
    ),
    Design(
        "reporting-guideline",
        ("research methodology", "reporting standards"),
        ("checklist", "equator network", "reporting items", "explanation and elaboration", "endorsed"),
        ("reporting guideline", "guideline for reporting", "consensus statement", "reporting statement"),
    ),
    Design(
        "prediction-model",
        ("prediction modeling", "clinical informatics"),
        ("area under the curve", "calibration", "validation cohort", "discrimination", "c-statistic"),
        ("prediction model", "risk score", "machine learning model"),
    ),
    Design(
        "psychometrics",
        ("psychometrics", "measurement science"),
        ("factor analysis", "internal consistency", "test-retest", "measurement invariance", "cronbach"),
        ("psychometric properties", "validation of the scale"),
    ),
    Design(
        "gwas",
        ("statistical genetics", "population genomics"),
        ("polygenic", "snp heritability", "genetic correlation", "linkage disequilibrium", "summary statistics"),
        ("genome-wide association", "gwas"),
    ),
    Design(
        "neuroimaging",
        ("neuroimaging", "computational neuroscience"),
        ("voxel", "cortical thickness", "connectivity", "diffusion tensor", "resting-state"),
        ("functional magnetic resonance", "fmri", "neuroimaging"),
    ),
    Design(
        "observational-cohort",
        ("epidemiology", "observational research"),
        ("follow-up", "hazard ratio", "incidence", "person-years", "baseline characteristics"),
        ("prospective cohort", "retrospective cohort", "cohort study"),
    ),
    Design(
        "case-control",
        ("epidemiology", "case-control research"),
        ("odds ratio", "matched controls", "recruited cases"),
        ("case-control", "case control study"),
    ),
    Design(
        "cross-sectional",
        ("epidemiology", "cross-sectional research"),
        ("prevalence", "survey", "questionnaire response rate"),
        ("cross-sectional",),
    ),
    Design(
        "qualitative-study",
        ("qualitative research", "health services research"),
        ("thematic analysis", "grounded theory", "focus group", "coding framework", "saturation"),
        ("semi-structured interview", "qualitative study"),
    ),
    Design(
        "mixed-methods",
        ("mixed methods research", "health services research"),
        ("quantitative and qualitative", "triangulation", "integration of findings"),
        ("mixed methods", "mixed-methods"),
    ),
    Design(
        "implementation-study",
        ("implementation science", "health services research"),
        ("implementation", "feasibility", "uptake", "barriers and facilitators", "pilot evaluation"),
        ("implementation study", "pilot evaluation", "feasibility study"),
    ),
    Design(
        "method-development",
        ("computational methods", "method development"),
        ("algorithm", "benchmark", "simulation", "software implementation", "runtime", "open source"),
        ("we developed", "new method", "toolkit"),
    ),
    Design(
        "case-report",
        ("clinical medicine", "case reporting"),
        ("presented to", "on examination", "was admitted", "differential diagnosis"),
        ("case report", "we report a case"),
    ),
    Design(
        "diagnostic-accuracy",
        ("clinical research", "diagnostic accuracy"),
        ("sensitivity", "specificity", "predictive value", "index test", "reference standard"),
        ("diagnostic accuracy", "stard"),
    ),
    Design(
        "narrative-review",
        ("evidence synthesis", "scientific review"),
        ("this review", "we review", "overview of", "state of the art", "current understanding"),
        ("narrative review", "scoping review"),
    ),
    Design(
        "commentary",
        ("scientific commentary", "scholarly communication"),
        ("we argue", "should be", "calls for", "in our view", "debate"),
        ("editorial", "commentary", "viewpoint", "perspective piece"),
    ),
    Design(
        "correspondence",
        ("scholarly communication", "post-publication review"),
        ("we note", "the authors report", "in reply"),
        ("letter to the editor", "we read with interest", "authors' reply"),
    ),
    Design(
        "economic-evaluation",
        ("health economics", "economic evaluation"),
        ("cost-effectiveness", "incremental cost", "quality-adjusted life", "willingness to pay"),
        ("economic evaluation", "cost-effectiveness analysis"),
    ),
)


def classify_design(
    title: str,
    abstract: str,
    body: str,
    article_type: str,
    preferred: tuple[str, ...] = (),
) -> tuple[str, list[str]]:
    """Return (category slug, research fields) from weighted term evidence.

    ``preferred`` carries the categories the resolved document profile expects,
    which breaks ties on papers whose subject matter and design share a
    vocabulary — a reporting guideline *about* systematic reviews, say.
    """
    title_text = normalize_prose(title).casefold()
    abstract_text = normalize_prose(abstract).casefold()
    body_text = normalize_prose(body[:160000]).casefold()
    scored: list[tuple[float, int, Design]] = []
    for order, design in enumerate(DESIGNS):
        score = 0.0
        for term in design.strong_terms:
            score += 12.0 * title_text.count(term)
            score += 5.0 * abstract_text.count(term)
            score += min(8.0, 2.5 * body_text.count(term))
        for term in design.terms:
            score += 4.0 * title_text.count(term)
            score += 1.5 * abstract_text.count(term)
            score += min(4.0, 0.4 * body_text.count(term))
        scored.append((score, -order, design))
    best_score, _order, best = max(scored)
    # A paper about systematic reviews is not itself a systematic review. When
    # the document profile expects a category and that category has real
    # support, it wins: the profile is resolved from stronger evidence.
    if preferred:
        candidates = [item for item in scored if item[2].category in preferred and item[0] >= 2.0]
        if candidates:
            preferred_score, _preferred_order, preferred_design = max(candidates)
            if preferred_score >= best_score * 0.45:
                best_score, best = preferred_score, preferred_design
    if best_score < 2.0:
        lowered = article_type.casefold()
        if "review" in lowered:
            return "narrative-review", ["evidence synthesis", "scientific review"]
        if "editorial" in lowered or "commentary" in lowered:
            return "commentary", ["scientific commentary", "scholarly communication"]
        return "observational-study", ["scientific research", "empirical research"]
    return best.category, list(best.research_fields)


ACRONYM_RE = re.compile(r"\(([A-Z][A-Za-z0-9+\-]{1,11})\)")
