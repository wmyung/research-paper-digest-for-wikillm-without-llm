"""Document profiles.

This module is dependency-free on purpose: the evidence ledger, the QA layer
and the compiler all read it, so it must sit below them in the import graph.

The eight level-2 headings of a WikiLLM source record are fixed, but what
belongs under them is not: a study protocol has no results to report, and an
editorial has an argument rather than a study design. A profile records that
difference as (a) which digest targets apply, (b) the sub-heading each section
carries, and (c) the evidence slots a complete record of this document type
should cover. The coverage ledger in :mod:`paper_digest.evidence` is built from
those slots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EvidenceSlot:
    id: str
    heading: str
    patterns: tuple[str, ...]
    sections: tuple[str, ...] = ()
    required: bool = True


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    key: str
    label: str
    subheadings: dict[str, str]
    applicable_targets: frozenset[str]
    slots: tuple[EvidenceSlot, ...]
    strong_signals: tuple[str, ...] = ()
    weak_signals: tuple[str, ...] = ()
    absent_signals: tuple[str, ...] = ()
    # Study-design slugs this document type usually carries; used to break ties
    # in the category taxonomy.
    category_bias: tuple[str, ...] = ()
    budget_scale: dict[str, float] = field(default_factory=dict)
    notes: str = ""


_COMMON_SLOTS = (
    EvidenceSlot(
        "objective_or_question",
        "1. Document Information",
        (
            r"\baim(?:ed|s)? to\b",
            r"\bobjectives?\b",
            r"\bresearch questions?\b",
            r"\bwe (?:sought|set out|present|report|describe|introduce|developed?|updated?|evaluated?|examined?)\b",
            r"\bthis (?:study|paper|review|article|statement|guideline) (?:aims?|aimed|presents?|reports?|describes?|examines?|replaces?|provides?)\b",
            r"\bthe (?:goal|purpose|aim) of\b",
            r"\bin this (?:article|paper|study|review)\b",
        ),
        ("Abstract", "Objectives", "Introduction"),
    ),
    EvidenceSlot(
        "data_or_code_availability",
        "1. Document Information",
        (
            r"\bdata (?:are|is|were) available\b",
            r"\bavailability\b",
            r"\baccession\b",
            r"\brepository\b",
            r"github\.com",
        ),
        ("Data availability", "Code availability", "Abstract", "Methods"),
        required=False,
    ),
    EvidenceSlot(
        "limitations_or_boundaries",
        "5. Limitations and Future Work",
        (
            r"\blimitations?\b",
            r"\bcaveats?\b",
            r"\bcannot\b",
            r"\bcould not\b",
            r"\bgenerali[sz]",
            r"\bfuture (?:studies|research|work)\b",
        ),
        ("Limitations", "Discussion", "Conclusion"),
    ),
    EvidenceSlot(
        "relation_to_prior_work",
        "6. Related Work",
        (
            r"\bprevious\w*\b",
            r"\bprior (?:work|studies|version|guidance)\b",
            r"\bconsistent with\b",
            r"\bet al\.",
            r"\bin contrast\b",
            r"\bearlier (?:studies|work|version|statement)\b",
            r"\bsince (?:the )?publication of\b",
            r"\bhave been (?:proposed|developed|reported|published|evaluated)\b",
            r"\bother (?:studies|reviews|guidelines|authors)\b",
        ),
        ("Introduction", "Discussion"),
    ),
)

_EMPIRICAL_SLOTS = (
    EvidenceSlot(
        "study_design",
        "3. Methodology and Architecture",
        (
            r"\b(?:cohort|case-control|cross-sectional|randomi[sz]ed|trial|prospective|retrospective|mixed methods|qualitative)\b",
        ),
        ("Methods", "Abstract"),
    ),
    EvidenceSlot(
        "population_and_setting",
        "3. Methodology and Architecture",
        (
            r"\bparticipants?\b",
            r"\bpatients?\b",
            r"\brecruit\w*\b",
            r"\benrol\w*\b",
            r"\binclusion criteria\b",
            r"\bsetting\b",
        ),
        ("Methods", "Abstract"),
    ),
    EvidenceSlot(
        "measures_and_variables",
        "3. Methodology and Architecture",
        (
            r"\bmeasure[sd]?\b",
            r"\bassessed\b",
            r"\boutcomes?\b",
            r"\bexposure\b",
            r"\bquestionnaire\b",
            r"\binstrument\b",
        ),
        ("Methods",),
    ),
    EvidenceSlot(
        "analysis_strategy",
        "3. Methodology and Architecture",
        (
            r"\bregression\b",
            r"\bmodel(?:s|led|ed)?\b",
            r"\badjusted for\b",
            r"\bstatistical analys[ei]s\b",
            r"\bsoftware\b",
        ),
        ("Methods",),
    ),
    EvidenceSlot(
        "primary_result_with_effect_size",
        "4. Key Results and Benchmarks",
        (r"\b\d+(?:\.\d+)?\s*%", r"\b95\s*%\s*(?:CI|confidence)", r"\bp\s*[<=>]", r"\b(?:OR|HR|RR|aOR)\b"),
        ("Results", "Abstract"),
    ),
    EvidenceSlot(
        "subgroup_or_sensitivity_analysis",
        "4. Key Results and Benchmarks",
        (r"\bsubgroup\b", r"\bsensitivity analys[ei]s\b", r"\bstratified\b", r"\binteraction\b"),
        ("Results", "Methods"),
        required=False,
    ),
    EvidenceSlot(
        "null_or_negative_finding",
        "4. Key Results and Benchmarks",
        (
            r"\bno (?:significant|association|difference|evidence)\b",
            r"\bnot (?:significant|associated)\b",
            r"\bdid not differ\b",
        ),
        ("Results", "Abstract", "Discussion"),
        required=False,
    ),
    EvidenceSlot(
        "ethics_or_governance",
        "1. Document Information",
        (r"\bethics\b", r"\bapproved by\b", r"\binformed consent\b", r"\binstitutional review board\b"),
        ("Methods", "Ethics"),
        required=False,
    ),
)

_REVIEW_SLOTS = (
    EvidenceSlot(
        "search_strategy",
        "3. Methodology and Architecture",
        (r"\bsearch(?:ed|es)?\b", r"\bdatabases?\b", r"\bmedline\b", r"\bembase\b", r"\bsearch strategy\b"),
        ("Methods", "Abstract"),
    ),
    EvidenceSlot(
        "eligibility_criteria",
        "3. Methodology and Architecture",
        (r"\beligib\w*\b", r"\binclusion criteria\b", r"\bexclusion criteria\b", r"\bpicos?\b"),
        ("Methods",),
    ),
    EvidenceSlot(
        "screening_and_extraction",
        "3. Methodology and Architecture",
        (r"\bscreen\w*\b", r"\bdata extraction\b", r"\btwo reviewers\b", r"\bindependently\b"),
        ("Methods",),
    ),
    EvidenceSlot(
        "risk_of_bias_assessment",
        "3. Methodology and Architecture",
        (r"\brisk of bias\b", r"\bquality assessment\b", r"\brobins\b", r"\bnewcastle-ottawa\b", r"\bgrade\b"),
        ("Methods", "Results"),
    ),
    EvidenceSlot(
        "included_studies_count",
        "4. Key Results and Benchmarks",
        (r"\b\d+\s+(?:studies|trials|records|articles|reports)\b", r"\bincluded\s+\d+\b"),
        ("Results", "Abstract"),
    ),
    EvidenceSlot(
        "pooled_estimate_or_synthesis",
        "4. Key Results and Benchmarks",
        (r"\bpooled\b", r"\bsummary estimate\b", r"\bmeta-analys[ei]s\b", r"\bsynthesis\b", r"\b95\s*%\s*CI\b"),
        ("Results", "Abstract"),
    ),
    EvidenceSlot(
        "heterogeneity_assessment",
        "4. Key Results and Benchmarks",
        (r"\bheterogeneity\b", r"\bI\s*2\b", r"\btau\s*2\b", r"\bsubgroup analys[ei]s\b"),
        ("Results",),
        required=False,
    ),
    EvidenceSlot(
        "certainty_of_evidence",
        "5. Limitations and Future Work",
        (r"\bcertainty\b", r"\bconfidence in the evidence\b", r"\bgrade\b", r"\bpublication bias\b"),
        ("Results", "Discussion"),
        required=False,
    ),
)

_METHOD_SLOTS = (
    EvidenceSlot(
        "problem_statement",
        "2. Key Contributions",
        (r"\bexisting (?:methods|approaches|tools)\b", r"\blimitation of\b", r"\bchallenge\b", r"\bbottleneck\b"),
        ("Introduction", "Abstract"),
    ),
    EvidenceSlot(
        "algorithm_or_model",
        "3. Methodology and Architecture",
        (
            r"\balgorithm\b",
            r"\bmodel\b",
            r"\barchitecture\b",
            r"\bloss function\b",
            r"\bestimator\b",
            r"\blikelihood\b",
        ),
        ("Methods", "Results"),
    ),
    EvidenceSlot(
        "implementation_and_availability",
        "1. Document Information",
        (r"\bimplemented in\b", r"\bopen source\b", r"github\.com", r"\bversion \d", r"\bpackage\b"),
        ("Methods", "Code availability", "Data availability"),
    ),
    EvidenceSlot(
        "benchmark_datasets",
        "3. Methodology and Architecture",
        (r"\bbenchmark\b", r"\bdatasets?\b", r"\bsimulat\w*\b", r"\bevaluation (?:set|data)\b"),
        ("Methods", "Results"),
    ),
    EvidenceSlot(
        "comparison_with_baselines",
        "4. Key Results and Benchmarks",
        (r"\bcompared (?:with|to)\b", r"\bbaseline\b", r"\boutperform\w*\b", r"\bstate of the art\b", r"\bversus\b"),
        ("Results", "Abstract"),
    ),
    EvidenceSlot(
        "performance_metrics",
        "4. Key Results and Benchmarks",
        (
            r"\bAUC\b",
            r"\baccuracy\b",
            r"\bprecision\b",
            r"\brecall\b",
            r"\bF1\b",
            r"\bruntime\b",
            r"\bpower\b",
            r"\bfalse positive\b",
        ),
        ("Results", "Abstract"),
    ),
    EvidenceSlot(
        "failure_modes_or_assumptions",
        "5. Limitations and Future Work",
        (r"\bassum\w*\b", r"\bfails? (?:when|to)\b", r"\bsensitive to\b", r"\brequires?\b"),
        ("Discussion", "Limitations", "Methods"),
        required=False,
    ),
)

_ARGUMENT_SLOTS = (
    EvidenceSlot(
        "position_or_thesis",
        "2. Key Contributions",
        (r"\bwe argue\b", r"\bshould\b", r"\bmust\b", r"\bwe believe\b", r"\bthe case for\b", r"\bcall for\b"),
        ("Abstract", "Introduction", "Discussion", "Front matter"),
    ),
    EvidenceSlot(
        "evidence_base_cited",
        "3. Methodology and Architecture",
        (r"\bet al\.", r"\bstudies (?:have|show)\b", r"\bevidence\b", r"\bdata (?:show|suggest)\b"),
        ("Introduction", "Discussion"),
    ),
    EvidenceSlot(
        "counterarguments_or_caveats",
        "5. Limitations and Future Work",
        (r"\bhowever\b", r"\bcritics?\b", r"\bcounter\w*\b", r"\bcaveats?\b", r"\bcaution\b"),
        ("Discussion", "Conclusion"),
        required=False,
    ),
    EvidenceSlot(
        "recommended_action",
        "5. Limitations and Future Work",
        (r"\bwe recommend\b", r"\bshould be\b", r"\bfuture\b", r"\bnext steps?\b", r"\bpolicy\b"),
        ("Discussion", "Conclusion"),
    ),
)


PROFILES: tuple[DocumentProfile, ...] = (
    DocumentProfile(
        key="empirical_research",
        label="Empirical research study",
        subheadings={
            "information": "Study scope and source availability",
            "methods": "Design, data, measurements, and analysis",
            "results": "Primary, secondary, and boundary findings",
            "related": "Prior evidence and methodological context",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS + _EMPIRICAL_SLOTS,
        strong_signals=(r"\bwe (?:recruited|enrolled|randomi[sz]ed|surveyed|interviewed)\b", r"\bparticipants were\b"),
        weak_signals=(r"\bcohort\b", r"\bbaseline characteristics\b", r"\bodds ratio\b", r"\bhazard ratio\b"),
    ),
    DocumentProfile(
        key="systematic_review_meta_analysis",
        category_bias=("meta-analysis", "systematic-review"),
        label="Systematic review or meta-analysis",
        subheadings={
            "information": "Review scope, registration, and source availability",
            "methods": "Search, eligibility, appraisal, and synthesis",
            "results": "Included evidence and synthesised estimates",
            "related": "Relation to previous syntheses",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS + _REVIEW_SLOTS,
        strong_signals=(
            r"\bwe (?:systematically )?searched\b",
            r"\bPROSPERO\b",
            r"\brecords were screened\b",
            r"\bstudies were included\b",
            r"\bwe (?:conducted|performed|report) a (?:systematic review|meta-analys[ei]s)\b",
            r"\bpooled (?:estimate|effect|odds|risk)\b",
        ),
        weak_signals=(r"\bheterogeneity\b", r"\brisk of bias\b", r"\bforest plot\b", r"\bdata extraction\b"),
    ),
    DocumentProfile(
        key="methods_tool",
        category_bias=("method-development", "prediction-model"),
        label="Method, model, or software contribution",
        subheadings={
            "information": "Tool scope, implementation, and availability",
            "methods": "Model, algorithm, and evaluation design",
            "results": "Benchmarks and comparative performance",
            "related": "Existing methods and baselines",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS + _METHOD_SLOTS,
        strong_signals=(
            r"\bwe (?:present|introduce|developed?|propose)\s+\w+,?\s+an?\b",
            r"\bopen[- ]source\b",
            r"\bavailable at https?://github",
        ),
        weak_signals=(r"\balgorithm\b", r"\bbenchmark\b", r"\bimplementation\b", r"\bruntime\b"),
    ),
    DocumentProfile(
        key="study_protocol",
        label="Study protocol",
        subheadings={
            "information": "Protocol scope, registration, and status",
            "methods": "Planned design, population, and analysis",
            "results": "Planned outputs and analysis outputs (not yet reported)",
            "related": "Rationale from prior evidence",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "limitations", "related"}),
        slots=_COMMON_SLOTS
        + tuple(
            slot
            for slot in _EMPIRICAL_SLOTS
            if slot.id
            not in {"primary_result_with_effect_size", "null_or_negative_finding", "subgroup_or_sensitivity_analysis"}
        ),
        strong_signals=(
            r"\bstudy protocol\b",
            r"\bthis protocol describes\b",
            r"\bwill be (?:recruited|randomi[sz]ed|collected|analysed|analyzed)\b",
        ),
        weak_signals=(r"\bplanned analys[ei]s\b", r"\btrial registration\b"),
        notes="A protocol reports no findings; the results section states that explicitly rather than inventing outcomes.",
    ),
    DocumentProfile(
        key="narrative_review",
        category_bias=("narrative-review",),
        label="Narrative or scoping review",
        subheadings={
            "information": "Review scope and sources consulted",
            "methods": "Scope, selection approach, and organising framework",
            "results": "Principal themes and reported evidence",
            "related": "Positioning within the literature",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS
        + (
            EvidenceSlot(
                "scope_of_review",
                "3. Methodology and Architecture",
                (r"\bthis review\b", r"\bwe review\b", r"\bscope\b"),
                ("Abstract", "Introduction"),
            ),
            EvidenceSlot(
                "themes_or_organising_framework",
                "4. Key Results and Benchmarks",
                (r"\bthemes?\b", r"\bframework\b", r"\bwe organise\b", r"\bcategories\b"),
                ("Results", "Discussion"),
            ),
            EvidenceSlot(
                "open_questions",
                "5. Limitations and Future Work",
                (r"\bunresolved\b", r"\bopen questions?\b", r"\bfuture (?:research|work)\b", r"\bremains? unclear\b"),
                ("Discussion", "Conclusion"),
            ),
        ),
        strong_signals=(r"\bnarrative review\b", r"\bin this review\b", r"\bwe review\b"),
        weak_signals=(r"\boverview\b", r"\bstate of the art\b"),
    ),
    DocumentProfile(
        key="case_report",
        category_bias=("case-report",),
        label="Case report or case series",
        subheadings={
            "information": "Case scope, consent, and reporting standard",
            "methods": "Presentation, investigations, and management",
            "results": "Clinical course and outcome",
            "related": "Comparable reported cases",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS
        + (
            EvidenceSlot(
                "case_presentation",
                "3. Methodology and Architecture",
                (r"\bpresented (?:with|to)\b", r"\bwas admitted\b", r"\ba \d+-year-old\b"),
                ("Methods", "Results"),
            ),
            EvidenceSlot(
                "investigations",
                "3. Methodology and Architecture",
                (r"\bimaging\b", r"\blaborator\w*\b", r"\bbiopsy\b", r"\bexamination\b"),
                ("Methods", "Results"),
            ),
            EvidenceSlot(
                "management_and_outcome",
                "4. Key Results and Benchmarks",
                (r"\btreated with\b", r"\bfollow-?up\b", r"\bdischarged\b", r"\bresolved\b", r"\boutcome\b"),
                ("Results",),
            ),
            EvidenceSlot(
                "consent", "1. Document Information", (r"\bconsent\b",), ("Ethics", "Methods"), required=False
            ),
        ),
        strong_signals=(
            r"\bcase report\b",
            r"\bwe report (?:a|the) case\b",
            r"\b\d{1,3}-year-old (?:man|woman|male|female|boy|girl)\b",
        ),
    ),
    DocumentProfile(
        key="guideline_consensus",
        category_bias=("reporting-guideline",),
        label="Guideline, consensus, or reporting standard",
        subheadings={
            "information": "Guideline scope, sponsor, and intended users",
            "methods": "Development process and consensus procedure",
            "results": "Recommendations and items",
            "related": "Relation to previous guidance",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS
        + (
            EvidenceSlot(
                "development_process",
                "3. Methodology and Architecture",
                (
                    r"\bdelphi\b",
                    r"\bconsensus\b",
                    r"\bpanel\b",
                    r"\bworking group\b",
                    r"\bwe updated\b",
                    r"\bdevelop\w*\b",
                    r"\bsurvey\b",
                    r"\bin-person meeting\b",
                    r"\bwe invited\b",
                ),
                ("Methods", "Abstract", "Results"),
            ),
            EvidenceSlot(
                "panel_composition",
                "3. Methodology and Architecture",
                (r"\bpanel(?:lists)?\b", r"\bmembers\b", r"\bexperts?\b", r"\bstakeholders?\b"),
                ("Methods",),
                required=False,
            ),
            EvidenceSlot(
                "recommendations_or_items",
                "4. Key Results and Benchmarks",
                (r"\bcheck ?list\b", r"\bitems?\b", r"\brecommend\w*\b", r"\bstatements?\b"),
                ("Results", "Abstract"),
            ),
            EvidenceSlot(
                "scope_of_application",
                "1. Document Information",
                (r"\bintended for\b", r"\bapplies to\b", r"\bshould (?:be used|not be used)\b", r"\bscope\b"),
                ("Introduction", "Discussion"),
            ),
            EvidenceSlot(
                "implementation_guidance",
                "5. Limitations and Future Work",
                (r"\bhow to use\b", r"\bimplementation\b", r"\bendorse\w*\b", r"\bdissemination\b"),
                ("Discussion", "Conclusion"),
                required=False,
            ),
        ),
        strong_signals=(
            r"\breporting guideline\b",
            r"\bconsensus statement\b",
            r"\bguideline for reporting\b",
            r"\b(?:statement|guideline)\b[^.]{0,60}\b(?:update[sd]?|replaces)\b",
            r"\bwe recommend (?:that )?authors\b",
            r"\bthis (?:statement|guideline) (?:replaces|is intended|provides)\b",
            r"\b\d{1,3}-item checklist\b",
        ),
        weak_signals=(r"\bequator\b", r"\bdelphi\b", r"\bchecklist\b", r"\bpanel\b", r"\bendorse\w*\b"),
    ),
    DocumentProfile(
        key="editorial_commentary",
        category_bias=("commentary",),
        label="Editorial, commentary, or perspective",
        subheadings={
            "information": "Piece scope and standing",
            "methods": "Evidence base and structure of the argument",
            "results": "Claims advanced",
            "related": "Debate this piece joins",
        },
        applicable_targets=frozenset({"information", "contributions", "methods", "results", "limitations", "related"}),
        slots=_COMMON_SLOTS + _ARGUMENT_SLOTS,
        strong_signals=(r"\beditorial\b", r"\bcommentary\b", r"\bperspective\b", r"\bviewpoint\b", r"\bwe argue\b"),
        notes="An opinion piece reports an argument, not a study design.",
    ),
    DocumentProfile(
        key="letter_response_correspondence",
        category_bias=("correspondence",),
        label="Letter, response, or correspondence",
        subheadings={
            "information": "Correspondence scope and the work it addresses",
            "methods": "Basis of the response",
            "results": "Points raised",
            "related": "The exchange this belongs to",
        },
        applicable_targets=frozenset({"information", "contributions", "results", "related"}),
        slots=_COMMON_SLOTS[:1]
        + (
            EvidenceSlot(
                "target_of_response",
                "1. Document Information",
                (
                    r"\bin (?:their|the) (?:recent )?(?:paper|article|study)\b",
                    r"\bet al\.\s+(?:report|describe|argue)",
                    r"\bwe read with interest\b",
                ),
                ("Front matter", "Abstract", "Introduction"),
            ),
            EvidenceSlot(
                "points_raised",
                "4. Key Results and Benchmarks",
                (r"\bhowever\b", r"\bwe disagree\b", r"\bconcerns?\b", r"\bwe note\b"),
                ("Discussion", "Front matter"),
            ),
        ),
        strong_signals=(
            r"\bwe read with (?:great )?interest\b",
            r"\bletter to the editor\b",
            r"\bin response to\b",
            r"\bauthors'? reply\b",
        ),
        notes="Correspondence is short; a thin record is expected rather than a defect.",
    ),
    DocumentProfile(
        key="excluded_non_paper",
        label="Non-article document",
        subheadings={
            "information": "Document scope",
            "methods": "Structure",
            "results": "Content",
            "related": "Context",
        },
        applicable_targets=frozenset({"information"}),
        slots=_COMMON_SLOTS[:1],
        strong_signals=(
            r"\bcorrection\b",
            r"\berratum\b",
            r"\bretraction (?:notice)?\b",
            r"\bexpression of concern\b",
            r"\btable of contents\b",
        ),
        notes="Corrections, errata and retraction notices are recorded, not digested as independent studies.",
    ),
)

PROFILES_BY_KEY = {profile.key: profile for profile in PROFILES}
DEFAULT_PROFILE = PROFILES_BY_KEY["empirical_research"]


def _count(patterns: tuple[str, ...], text: str) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.I))


ARTICLE_TYPE_PRIORS: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (
        re.compile(r"\b(?:correspondence|letter|author(?:s)? reply|response)\b", re.I),
        "letter_response_correspondence",
        9.0,
    ),
    (re.compile(r"\b(?:editorial|commentary|perspective|viewpoint)\b", re.I), "editorial_commentary", 9.0),
    (
        re.compile(r"\b(?:systematic review|meta[- ]analysis|scoping review)\b", re.I),
        "systematic_review_meta_analysis",
        10.0,
    ),
    (re.compile(r"\b(?:review article|narrative review|review)\b", re.I), "narrative_review", 5.0),
    (re.compile(r"\b(?:study protocol|protocol)\b", re.I), "study_protocol", 9.0),
    (re.compile(r"\bcase (?:report|series)\b", re.I), "case_report", 9.0),
    (re.compile(r"\b(?:guideline|consensus|position statement|recommendation)\b", re.I), "guideline_consensus", 9.0),
    (re.compile(r"\b(?:methods? article|software|tool|resource)\b", re.I), "methods_tool", 7.0),
    (re.compile(r"\b(?:research article|original article|clinical trial)\b", re.I), "empirical_research", 6.0),
    (re.compile(r"\b(?:correction|erratum|retraction|expression of concern)\b", re.I), "excluded_non_paper", 12.0),
)


def classify_document(
    title: str,
    abstract: str,
    body: str,
    article_type: str,
    *,
    section_names: set[str] | None = None,
    page_count: int | None = None,
) -> tuple[DocumentProfile, list[tuple[str, float]]]:
    """Pick a document profile from lexical, metadata and structural evidence.

    Publisher article-type labels and real section topology are treated as
    priors, not absolute overrides. This corrects short correspondence and
    reviews before empirical-only coverage gates are applied while still
    allowing strong content evidence to win a contradictory label.
    """
    head = f"{title}\n{article_type}\n{abstract}"
    corpus = body[:120000]
    section_names = section_names or set()
    has_methods_results = {"Methods", "Results"} <= section_names
    scores: list[tuple[float, int, DocumentProfile]] = []
    for order, profile in enumerate(PROFILES):
        score = 0.0
        score += 5.0 * _count(profile.strong_signals, title)
        score += 3.0 * _count(profile.strong_signals, head)
        score += 1.2 * _count(profile.strong_signals, corpus)
        score += 2.0 * _count(profile.weak_signals, title)
        score += 1.0 * _count(profile.weak_signals, head)
        score += 0.4 * _count(profile.weak_signals, corpus)
        for pattern, profile_key, weight in ARTICLE_TYPE_PRIORS:
            if profile.key == profile_key and pattern.search(article_type or ""):
                score += weight
        if has_methods_results and profile.key == "empirical_research":
            score += 4.0
        if "Methods" in section_names and profile.key in {
            "systematic_review_meta_analysis",
            "methods_tool",
            "study_protocol",
            "guideline_consensus",
        }:
            score += 1.0
        short_non_imrad = bool(page_count and page_count <= 3 and not has_methods_results)
        if short_non_imrad and profile.key in {"letter_response_correspondence", "editorial_commentary"}:
            score += 1.5
        if has_methods_results and profile.key in {"letter_response_correspondence", "editorial_commentary"}:
            score -= 2.5
        scores.append((score, -order, profile))
    scores.sort(reverse=True)
    best = scores[0]
    ranking = [(item[2].key, round(item[0], 3)) for item in scores[:5]]
    if best[0] < 2.0:
        return DEFAULT_PROFILE, ranking
    return best[2], ranking
