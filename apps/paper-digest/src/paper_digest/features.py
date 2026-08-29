"""Sentence-level feature extraction for evidence selection.

Selection quality is driven by what a sentence *is*, not by which keywords it
happens to contain. Each probe below is a deterministic regular expression over
one sentence; the profile layer combines them into per-target scores. The
"relational" score implements the retrieval-writing standard: a good retrieval
unit names an entity, a population, a comparison, a direction, and a magnitude.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .text import word_count

EFFECT_RE = re.compile(
    r"\b(?:odds ratio|hazard ratio|risk ratio|rate ratio|relative risk|mean difference|"
    r"standardi[sz]ed mean difference|prevalence ratio|incidence rate|"
    r"OR|HR|RR|aOR|aHR|SMD|MD|IRR|AUC|AUROC|ICC|r_?g|R\^?2|β|beta coefficient)\s*[=:(]|"
    r"\b\d+(?:\.\d+)?\s*%|\b95\s*%\s*(?:CI|confidence interval)|\bp\s*[<=>]\s*0?\.\d+|"
    r"\bP\s*[<=>]\s*\d|\bn\s*=\s*\d+|\bN\s*=\s*\d+|×\s*10\^?-?\d+",
    re.I,
)
COMPARISON_RE = re.compile(
    r"\b(?:compared (?:with|to)|relative to|versus|vs\.?|than|between groups|"
    r"outperform\w*|exceeded|no different|similar to|in contrast (?:to|with)|"
    r"whereas|while|against a?\s*baseline)\b",
    re.I,
)
DIRECTION_RE = re.compile(
    r"\b(?:higher|lower|greater|smaller|larger|increase[sd]?|decrease[sd]?|reduced|reduction|"
    r"improve[sd]?|improvement|worse|better|rose|fell|declined|elevated|attenuated|"
    r"more likely|less likely|positive(?:ly)? associated|negative(?:ly)? associated|"
    r"protective|inverse)\b",
    re.I,
)
POPULATION_RE = re.compile(
    r"\b(?:participants?|patients?|subjects?|individuals?|respondents?|clients?|cases?|controls?|"
    r"cohorts?|samples?|children|adults?|adolescents?|women|men|immigrants?|households?|"
    r"volunteers?|animals?|mice|rats|cells?|datasets?|records?|observations?|"
    r"n\s*=\s*\d+|\b\d{2,}\s+(?:participants?|patients?|individuals?|people|clients?))\b",
    re.I,
)
HEDGE_RE = re.compile(
    r"\b(?:may|might|could|possibly|potentially|suggests?|appears?|seems?|likely|"
    r"we speculate|it is plausible)\b",
    re.I,
)
SELF_REFERENCE_RE = re.compile(
    r"\b(?:we|our|us|this (?:study|paper|work|article|review|analysis)|"
    r"the (?:present|current) (?:study|work|analysis)|here (?:we|the))\b",
    re.I,
)
NOVELTY_RE = re.compile(
    r"\b(?:we (?:present|propose|introduce|develop|developed|describe|report|show|"
    r"demonstrate|found|find|provide|derive|construct|implement|extend|updated?)|"
    r"to (?:our|the) knowledge|for the first time|the first (?:study|report|analysis)|"
    r"this (?:study|paper|work) (?:is|provides|presents|shows|demonstrates|extends)|"
    r"novel|we recommend)\b",
    re.I,
)
# A limitation is either explicitly named, or is a first-person statement of
# something the authors could not do. "X could not believe Y" is neither.
LIMITATION_STRONG_RE = re.compile(
    r"\b(?:limitations?|caveats?|should be interpreted with caution|may not generali[sz]e|"
    r"generali[sz]ability|small sample size|underpowered|underrepresent\w*|selection bias|"
    r"residual confounding|recall bias|measurement error|"
    r"future (?:studies|research|work)|further (?:studies|research|work) (?:is|are|will)|"
    r"remains? unclear|beyond the scope)\b",
    re.I,
)
LIMITATION_WEAK_RE = re.compile(
    r"\b(?:cannot|could not|was not able|were not able|unable to|not possible to|"
    r"did not (?:assess|measure|examine|allow|include|permit|collect|capture)|"
    r"were excluded|too small)\b",
    re.I,
)
METHOD_RE = re.compile(
    r"\b(?:recruited|enrolled|randomi[sz]ed|allocated|sampled|measured|assessed|administered|"
    r"conducted|performed|calculated|estimated|fitted?|modelled|modeled|adjusted for|"
    r"regression|analysis of variance|questionnaire|interview(?:ed|s)?|protocol|inclusion criteria|"
    r"exclusion criteria|follow-?up|outcome measures?|primary outcome|secondary outcome|"
    r"software|version \d|algorithm|implemented|pipeline|dataset|sequencing|imputation|"
    r"we (?:reviewed|evaluated|surveyed|searched|screened|extracted|selected|drafted|invited|"
    r"updated|developed|compiled|collected|coded|piloted|tested|applied|used|followed)|"
    r"were (?:reviewed|evaluated|surveyed|searched|screened|extracted|selected|collected|invited)|"
    r"consensus|delphi|panel|working group|steering committee|in-person meeting|"
    r"was developed|were developed|development of|search strateg|data extraction|"
    r"eligibility criteria|coding|thematic analysis|sensitivity analysis|"
    r"guidance for developing|according to (?:the )?(?:protocol|guidance|criteria))\b",
    re.I,
)
DATA_AVAILABILITY_RE = re.compile(
    r"\b(?:data (?:are|is|were|will be) available|available (?:from|at|on|in)|"
    r"deposited (?:in|at)|accession (?:number|code)|repository|github\.com|zenodo|dryad|"
    r"upon reasonable request|code (?:is|are) available|open source|under (?:the )?(?:CC|MIT|GPL))\b",
    re.I,
)
OBJECTIVE_RE = re.compile(
    r"\b(?:aim(?:ed|s)? to|objectives? (?:of|were|was|is|are)|the (?:goal|purpose) (?:of|was|is)|"
    r"we (?:sought|set out|aimed|investigated|examined|evaluated|assessed|tested) |"
    r"this (?:study|paper|review|work) (?:aims?|aimed|examines?|investigates?|evaluates?|"
    r"assesses|addresses|reports)|research questions?)\b",
    re.I,
)
RELATED_WORK_RE = re.compile(
    r"\b(?:previous(?:ly)?|prior (?:work|studies|research|version|guidance)|"
    r"earlier (?:studies|work|reports|version|statement)|"
    r"other (?:studies|authors|groups|work|reviews|guidelines)|"
    r"has been (?:reported|shown|described|proposed|developed|published)|"
    r"have been (?:reported|shown|described|proposed|developed|published|evaluated)|"
    r"have (?:reported|shown|described|proposed|found|evaluated|suggested)|"
    r"studies (?:suggest|show|report|indicate|have)|evidence from|"
    r"consistent with|in line with|compared with (?:previous|other|existing)|"
    r"in contrast (?:to|with)|et al\.|existing (?:methods|approaches|literature|tools|guidance)|"
    r"published in \d{4}|since (?:the )?publication of)\b",
    re.I,
)
NULL_RESULT_RE = re.compile(
    r"\b(?:no (?:significant|statistically significant|evidence of|association|difference|effect)|"
    r"not (?:significant|statistically significant|associated|different)|"
    r"did not (?:differ|reach|attain|show)|failed to|null (?:result|finding)|"
    r"remained non-?significant)\b",
    re.I,
)
# Publisher/structural noise that must never reach the digest.
# A dash-introduced gloss is a definition wherever it appears: glossary boxes
# run several of them together inside what the splitter sees as one sentence.
DEFINITION_RE = re.compile(
    r"^[A-Z][A-Za-z0-9 ,'’()/-]{2,60}\s*[—–]\s*[A-Z(]|"
    r"^[A-Z][A-Za-z0-9 -]{2,40}\s+(?:is|are) defined as\b|"
    r"^[A-Z][A-Za-z0-9 -]{2,40}\s+refers? to\b|"
    r"\s[A-Z][A-Za-z0-9 '’-]{2,40}\s*[—–]\s*(?:A|An|The|Any|Two)\s",
)
# "31 interventions proposed to ..." starts mid-clause: the extractor lost the
# opening words at a column break.
FRAGMENT_START_RE = re.compile(
    r"^\d+\s+[a-z]+s?\s+(?:proposed|reported|identified|included|described|published|"
    r"evaluated|conducted|performed|used|assessed|shown)\b"
)
INSTRUCTION_RE = re.compile(
    r"^(?:Specify|Describe|Present|Provide|Report|List|Identify|Indicate|State|Give|Explain|"
    r"Cite|Define|Summari[sz]e|Discuss|Acknowledge|Declare)\b\s+[a-z]",
)
SPEAKER_QUOTE_RE = re.compile(
    r"^[A-Z][A-Za-z .]{0,28}(?:PHS|participant|respondent|interviewee|nurse|physician|staff)[\w ]{0,10}\s*:", re.I
)
QUOTE_RE = re.compile(r"[“][^”]{40,}[”]")
CITATION_RE = re.compile(r"\[[0-9][0-9,\s–-]*\]|\([A-Z][A-Za-z’'-]+(?: et al\.)?,? \d{4}[a-z]?\)")
BOILERPLATE_RE = re.compile(
    r"©\s*\d{4}|\bpublished by [A-Z][A-Za-z&. ]+(?:Inc|Ltd|B\.V|Elsevier|Wiley|Springer)|"
    r"\b(?:creative commons|all rights reserved|publisher'?s note|springer nature remains|"
    r"the author\(s\) declare|conflicts? of interest|competing interests|"
    r"credit authorship contribution|we (?:thank|dedicate|acknowledge)|"
    r"supplementary (?:information|material) is available|reprints and permissions|"
    r"correspondence (?:and requests|should be))\b",
    re.I,
)
DISPLAY_DESCRIPTION_RE = re.compile(
    r"^(?:the\s+)?(?:dashed|solid|dotted|black|red|blue|grey|gray|horizontal|vertical|coloured|colored)\s+"
    r"(?:line|bar|area|band|region)\b|"
    r"^error bars?\b|^shaded (?:area|region)\b|^each (?:point|dot|bar|panel)\b|"
    r"^panels?\s+[a-h]\b|^data are (?:presented|shown|expressed)\b|"
    r"^abbreviations?\s*:|^values are\b|^bars? (?:show|represent|indicate)\b",
    re.I,
)
FIGURE_REFERENCE_RE = re.compile(r"\b(?:Fig(?:ure)?\.?\s*\d+|Table\s*\d+|Box\s*\d+|Supplementary\s+\w+\s*\d+)", re.I)
URL_RE = re.compile(r"https?://|www\.\w|doi\.org", re.I)
NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?%?")
# A function word followed straight by a clause-opening pronoun or determiner is
# ungrammatical, and marks two column fragments spliced together by extraction.
SPLICE_RE = re.compile(
    r"\b(?:of|for|with|from|by|to|in|on|at|and|or|that|which|than|as)\s+"
    r"(?:We|Our|This|These|Those|Their|It|They|There|He|She)\b"
)


@dataclass(slots=True)
class SentenceFeatures:
    words: int
    numbers: int
    numeric_ratio: float
    citation_count: int
    has_effect: bool
    has_comparison: bool
    has_direction: bool
    has_population: bool
    has_hedge: bool
    has_self_reference: bool
    has_novelty: bool
    has_limitation: bool
    has_limitation_strong: bool
    has_method: bool
    has_objective: bool
    has_related: bool
    has_null_result: bool
    has_data_availability: bool
    is_definition: bool
    is_instruction: bool
    is_display_description: bool
    is_quotation: bool
    is_quote_fragment: bool
    is_spliced: bool
    is_boilerplate: bool
    references_display: bool
    has_url: bool
    relational_score: int

    @property
    def is_structural_noise(self) -> bool:
        return (
            self.is_definition
            or self.is_instruction
            or self.is_boilerplate
            or self.is_quotation
            or self.is_quote_fragment
            or self.is_spliced
            or self.is_display_description
        )


def relational_components(text: str) -> int:
    """How many of entity / population / comparison / direction / magnitude are present.

    Five components make a self-contained retrieval unit; three or more is the
    practical threshold for a sentence that answers a question on its own.
    """
    return sum(
        (
            bool(re.search(r"\b[A-Z][A-Za-z0-9-]{2,}\b", text)),
            bool(POPULATION_RE.search(text)),
            bool(COMPARISON_RE.search(text)),
            bool(DIRECTION_RE.search(text)),
            bool(EFFECT_RE.search(text)),
        )
    )


def extract(text: str) -> SentenceFeatures:
    words = word_count(text)
    numbers = len(NUMBER_TOKEN_RE.findall(text))
    return SentenceFeatures(
        words=words,
        numbers=numbers,
        numeric_ratio=numbers / max(1, words),
        citation_count=len(CITATION_RE.findall(text)),
        has_effect=bool(EFFECT_RE.search(text)),
        has_comparison=bool(COMPARISON_RE.search(text)),
        has_direction=bool(DIRECTION_RE.search(text)),
        has_population=bool(POPULATION_RE.search(text)),
        has_hedge=bool(HEDGE_RE.search(text)),
        has_self_reference=bool(SELF_REFERENCE_RE.search(text)),
        has_novelty=bool(NOVELTY_RE.search(text)),
        has_limitation=bool(
            LIMITATION_STRONG_RE.search(text) or (LIMITATION_WEAK_RE.search(text) and SELF_REFERENCE_RE.search(text))
        ),
        has_limitation_strong=bool(LIMITATION_STRONG_RE.search(text)),
        has_method=bool(METHOD_RE.search(text)),
        has_objective=bool(OBJECTIVE_RE.search(text)),
        has_related=bool(RELATED_WORK_RE.search(text)),
        has_null_result=bool(NULL_RESULT_RE.search(text)),
        has_data_availability=bool(DATA_AVAILABILITY_RE.search(text)),
        is_definition=bool(DEFINITION_RE.search(text)),
        is_instruction=bool(INSTRUCTION_RE.match(text)),
        is_display_description=bool(DISPLAY_DESCRIPTION_RE.match(text)),
        is_quotation=bool(SPEAKER_QUOTE_RE.match(text) or QUOTE_RE.search(text)),
        # An unbalanced quotation mark means the sentence splitter cut across a
        # verbatim interview quotation.
        is_quote_fragment=(text.count("\u201d") != text.count("\u201c") or text.count('"') % 2 == 1),
        is_spliced=bool(SPLICE_RE.search(text) or FRAGMENT_START_RE.match(text)),
        is_boilerplate=bool(BOILERPLATE_RE.search(text)),
        references_display=bool(FIGURE_REFERENCE_RE.search(text)),
        has_url=bool(URL_RE.search(text)),
        relational_score=relational_components(text),
    )
