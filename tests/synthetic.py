"""Synthetic publisher PDFs with known ground truth.

Real papers cannot be committed to the repository, and a fixture that is only
extracted text cannot exercise the layout analysis. These builders draw PDFs
that reproduce the structures the pipeline has to survive: a repository cover
sheet, a running head, a two-column body, superscript affiliation markers on
the byline, a small-print table under its caption, and a reference list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0
MARGIN = 48.0
GUTTER = 24.0
COLUMN_WIDTH = (PAGE_WIDTH - 2 * MARGIN - GUTTER) / 2

BODY_SIZE = 10.0
SMALL_SIZE = 8.0
HEADING_SIZE = 12.0
TITLE_SIZE = 17.0


@dataclass(slots=True)
class SyntheticPaper:
    title: str = "Deterministic extraction of structured records from publisher PDFs"
    article_type: str = "RESEARCH ARTICLE"
    authors: str = "Aisha N. Okonkwo 1 , * , Bjorn Halvorsen 1 , 2 , Mei-Ling Chen 3 , Rafael de Souza 3"
    author_names: tuple[str, ...] = (
        "Aisha N. Okonkwo",
        "Bjorn Halvorsen",
        "Mei-Ling Chen",
        "Rafael de Souza",
    )
    affiliations: tuple[str, ...] = (
        "1 Department of Clinical Epidemiology, Northfield University, Northfield, United Kingdom",
        "2 Institute for Health Informatics, Bergen University Hospital, Bergen, Norway",
        "3 School of Public Health, Riverside University, Riverside, Brazil",
    )
    notes: tuple[str, ...] = (
        "* Corresponding author.",
        "E-mail address: a.okonkwo@northfield.ac.uk (A.N. Okonkwo).",
    )
    journal: str = "Journal of Reproducible Informatics"
    doi: str = "10.1234/jri.2024.0042"
    year: int = 2024
    volume: str = "18"
    issue: str = "3"
    pages: str = "211-226"
    received: str = "Received: 4 March 2024"
    accepted: str = "Accepted: 19 June 2024"
    published: str = "Published: 2 August 2024"
    keywords: str = "Keywords: Record linkage; Extraction quality; Reproducibility; Retrieval"
    abstract: tuple[tuple[str, str], ...] = (
        (
            "Background",
            "Structured records extracted from publisher PDFs underpin downstream retrieval, "
            "yet layout artifacts silently corrupt them.",
        ),
        (
            "Methods",
            "We evaluated a deterministic extraction pipeline on 412 articles drawn from nine "
            "publishers, measuring field accuracy against manually curated references and "
            "adjusting for publisher and page count.",
        ),
        (
            "Results",
            "Field accuracy was higher for the layout-aware pipeline than for the baseline "
            "(94.1% versus 71.8%, difference 22.3 percentage points, 95% CI 19.4 to 25.2, "
            "P < 0.001). Author-list accuracy did not differ between two-column and "
            "single-column layouts (P = 0.41).",
        ),
        (
            "Conclusions",
            "A layout-aware deterministic pipeline recovers publisher metadata more accurately "
            "than a text-order baseline, and the remaining errors concentrate in scanned "
            "supplements.",
        ),
    )
    cover_sheet: bool = False
    include_table: bool = True
    sections: tuple[tuple[str, tuple[str, ...]], ...] = field(
        default_factory=lambda: (
            (
                "1. Introduction",
                (
                    "Systematic collections of research articles increasingly feed retrieval systems that "
                    "answer questions directly from source records, and the quality of those answers is "
                    "bounded by the quality of the extraction that produced them. Previous work reported "
                    "that naive text extraction reorders two-column pages and fuses table cells into "
                    "running prose, and earlier studies have shown that such defects propagate silently "
                    "into downstream indexes, where they are far harder to detect than at ingestion time.",
                    "Existing methods rely on the order in which glyphs happen to appear in the content "
                    "stream of a document. That order reflects how the typesetting software emitted the "
                    "page, not how a reader traverses it. In contrast, layout-aware analysis recovers "
                    "column boundaries before reading order is fixed, so a sentence that continues across "
                    "a column break is reassembled rather than interleaved with its neighbour. We aimed to "
                    "quantify how much that difference matters for the bibliographic fields a retrieval "
                    "index depends on, and for the body prose those indexes actually return.",
                    "Reporting of extraction quality has itself been inconsistent. Other studies have "
                    "described accuracy on a single publisher or a single field, which makes results hard "
                    "to compare across pipelines, and several report only aggregate character error rates "
                    "that obscure whether the title or the author list was the field that failed. We "
                    "therefore prespecified a field-level outcome and applied it uniformly across the "
                    "corpus, so that a reader can see which field each pipeline loses and under which "
                    "layout conditions the loss occurs.",
                    "The objective of this study was to estimate the difference in field-level accuracy "
                    "between a layout-aware deterministic pipeline and a text-order baseline, and to "
                    "identify the document properties under which the difference is largest. A secondary "
                    "objective was to characterise the residual error of the better pipeline, because a "
                    "residual that concentrates in one document class can be addressed operationally "
                    "while one that is spread evenly cannot.",
                    "We present three contributions. We developed a column-recovery procedure that needs "
                    "no trained model and runs in under two seconds per article, we introduce a "
                    "field-level accuracy (FLA) outcome that is comparable across publishers because it "
                    "is defined per field rather than per character, and we show that the remaining "
                    "errors concentrate in documents without a usable text layer rather than being "
                    "distributed across the corpus.",
                ),
            ),
            (
                "2. Methods",
                (
                    "We assembled a corpus of 412 open-access articles from nine publishers, stratified by "
                    "layout so that single-column and two-column designs were equally represented. "
                    "Articles were eligible if the publisher deposited a born-digital version with an "
                    "embedded text layer and if the record carried a resolvable digital object identifier "
                    "(DOI). Two reviewers independently curated reference values for title, ordered "
                    "author list, journal, DOI and publication date, resolving disagreements by "
                    "discussion and recording the reason for each resolution.",
                    "Participants in the annotation study were 12 research librarians recruited from four "
                    "institutions. Each record was measured twice, at least two weeks apart, and we "
                    "adjusted for publisher and page count using a mixed-effects logistic regression "
                    "(MELR) model fitted with restricted maximum likelihood (REML). Publisher was entered "
                    "as a random intercept because layout conventions cluster within publisher. Analyses "
                    "were performed with a prespecified protocol registered before data collection began, "
                    "and no outcome was added after the corpus was assembled.",
                    "The primary outcome was field-level accuracy, defined as exact string agreement "
                    "after Unicode normalisation, case folding of the journal name, and removal of "
                    "trailing punctuation. Secondary outcomes were ordered-author-list accuracy, which "
                    "required both the set and the order of names to match, and the proportion of records "
                    "whose body prose contained at least one table fragment. A table fragment was defined "
                    "as a run of at least five words that appeared inside a detected table region on the "
                    "rendered page.",
                    "Column boundaries were recovered from an x-coverage histogram computed over every "
                    "text block on a page, with each block contributing its height to every horizontal "
                    "bin it spans. Runs of low coverage that spanned most of the page height were treated "
                    "as gutters, and the bands between them as columns. Blocks covering two or more bands "
                    "were emitted before the columns they interrupt, which reproduces the way a reader "
                    "handles a figure that spans the page.",
                    "Running heads were identified by cross-page recurrence after masking digits, so that "
                    "page numbers and dates did not defeat the match. A block recurring on at least 40 "
                    "per cent of pages in the top or bottom band was treated as furniture and excluded "
                    "from prose, and the recurring text was retained separately because it frequently "
                    "carries the journal name. Isolated page numbers were removed regardless of "
                    "recurrence.",
                    "Body text size was estimated in two passes. The first pass took the character "
                    "weighted modal size across the document, which is biased toward whichever of "
                    "references and tables occupies the most characters. The second pass re-estimated the "
                    "size from blocks the first pass had classified as body prose, and the page was then "
                    "classified again. This matters because the separation of display matter from prose "
                    "is expressed relative to the running-text size.",
                    "Sensitivity analyses repeated the primary comparison after excluding scanned "
                    "supplements, and after restricting the corpus to articles published within the last "
                    "five years. A prespecified subgroup analysis examined two-column and single-column "
                    "layouts separately, and a post-hoc analysis examined records carrying a repository "
                    "cover sheet, because those had been identified during piloting as a distinct failure "
                    "mode.",
                    "Inter-rater reliability was summarised with the intraclass correlation coefficient "
                    "(ICC) using a two-way random-effects model for absolute agreement. Software and data "
                    "are available under an open licence. The analysis code is deposited in a public "
                    "repository and the annotation spreadsheets are available from the corresponding "
                    "author on reasonable request. No identifiable data were collected from the "
                    "annotators beyond their institutional affiliation.",
                ),
            ),
            (
                "3. Results",
                (
                    "Field accuracy was 94.1 per cent for the layout-aware pipeline and 71.8 per cent for "
                    "the baseline, a difference of 22.3 percentage points (95 per cent confidence interval "
                    "(CI) 19.4 to 25.2, P < 0.001). Ordered author-list accuracy was 91.7 per cent versus "
                    "63.2 per cent (P < 0.001), and the gap was widest for bylines carrying superscript "
                    "affiliation markers, where the baseline retained the marker characters inside the "
                    "surname.",
                    "Accuracy did not differ between two-column and single-column layouts for the "
                    "layout-aware pipeline (94.4 per cent versus 93.8 per cent, P = 0.41), and no "
                    "significant interaction with publisher was detected. The baseline, by contrast, lost "
                    "14.6 percentage points moving from single-column to two-column layouts, which is the "
                    "difference the column-recovery step is intended to remove. Table fragments "
                    "contaminated 0.7 per cent of layout-aware records compared with 18.9 per cent of "
                    "baseline records.",
                    "Among the 24 records that remained incorrect under the layout-aware pipeline, 19 "
                    "were scanned supplements without a text layer, and the remaining 5 carried a "
                    "repository cover sheet that the baseline treated as the article front matter. "
                    "Optical character recognition (OCR) recovered text for 14 of those 19 supplements at "
                    "reduced accuracy, and the 5 cover-sheet records were corrected once cover-sheet "
                    "detection was enabled.",
                    "Median processing time was 1.8 seconds per article for the layout-aware pipeline "
                    "compared with 0.6 seconds for the baseline, a difference that did not affect "
                    "throughput at the corpus scale evaluated here. The additional time was dominated by "
                    "the second body-size estimation pass, which required a full re-classification of "
                    "every page.",
                    "Publication-date accuracy improved from 66.4 per cent to 92.9 per cent, and "
                    "journal-name accuracy from 74.5 per cent to 96.2 per cent. The journal-name gain "
                    "came almost entirely from reading the running head when the opening page carried no "
                    "masthead. Digital object identifier accuracy was high for both pipelines (98.8 per "
                    "cent versus 99.3 per cent, P = 0.22), which is expected because a DOI is a "
                    "distinctive string that survives reordering.",
                    "Inter-rater reliability was high for every curated field (ICC 0.94, 95 per cent CI "
                    "0.91 to 0.96). Disagreements concentrated on hyphenated surnames and on journal "
                    "names that differ between the masthead and the running head, and in both cases the "
                    "resolution rule was recorded before the comparison was run.",
                    "Excluding scanned supplements raised layout-aware accuracy to 97.6 per cent and "
                    "baseline accuracy to 74.9 per cent, so the difference between pipelines widened "
                    "rather than narrowed under that restriction. Restricting the corpus to the last five "
                    "years produced an almost identical estimate (22.1 percentage points, 95 per cent CI "
                    "18.7 to 25.5), indicating that the result is not driven by older typesetting.",
                ),
            ),
            (
                "4. Discussion",
                (
                    "These results are consistent with prior reports that extraction defects concentrate "
                    "at column boundaries and table margins. Other studies have proposed learned page "
                    "segmentation, but the deterministic approach evaluated here reaches comparable "
                    "accuracy without a model, without training data, and without the version drift that "
                    "a learned component introduces into a reproducible pipeline.",
                    "A limitation is that the corpus covered nine publishers and may not generalise to "
                    "layouts outside that sample. We could not measure accuracy on paywalled articles "
                    "because redistribution was not permitted, and residual confounding by publication "
                    "year cannot be excluded even though the restricted analysis was concordant. Future "
                    "research should extend the evaluation to scanned archives, where the failure mode is "
                    "different in kind rather than in degree.",
                    "A further limitation is that annotation used exact string agreement, which penalises "
                    "acceptable typographic variants such as an en dash standing in for a hyphen. We did "
                    "not assess semantic equivalence, so the reported accuracies are conservative for "
                    "both pipelines. The librarian annotators were recruited from four institutions in "
                    "one country, and their conventions for transliterating names may not transfer to "
                    "corpora dominated by other scripts.",
                    "Because the corpus was assembled from open-access articles, the findings may not "
                    "hold for publishers whose typesetting differs systematically from open-access "
                    "practice. Causality cannot be inferred from this design, and the comparison reflects "
                    "one baseline implementation rather than text-order extraction in general; a "
                    "different baseline with its own heuristics could close part of the gap without "
                    "recovering columns at all.",
                ),
            ),
            (
                "5. Conclusion",
                (
                    "A layout-aware deterministic pipeline recovers publisher metadata substantially more "
                    "accurately than a text-order baseline, and the errors that remain are concentrated "
                    "in documents without a usable text layer rather than spread across the corpus. That "
                    "concentration is what makes the residual tractable operationally.",
                ),
            ),
        )
    )
    references: tuple[str, ...] = (
        "1. Halvorsen B, Chen M-L. Layout analysis for scholarly documents. J Doc Eng 2021;14:88-101.",
        "2. de Souza R, Okonkwo AN. Reading order recovery in two-column articles. Inf Process 2022;58:1023-39.",
        "3. Chen M-L, et al. Table detection without supervision. Proc Doc Anal 2023;7:44-57.",
    )
    table_caption: str = "Table 1. Field-level accuracy by publisher and layout."
    table_rows: tuple[str, ...] = (
        "Publisher Layout Records Baseline Layout-aware",
        "Alpha Press two-column 62 70.9 93.5",
        "Beta Journals single-column 58 74.1 94.8",
        "Gamma Open two-column 71 68.3 95.1",
        "Delta Society single-column 44 77.2 92.6",
        "Epsilon Media two-column 55 69.5 94.0",
    )


def _wrap(text: str, width: float, size: float, bold: bool) -> list[str]:
    """Greedy word wrap measured with the real font metrics."""
    font = "hebo" if bold else "helv"
    lines: list[str] = []
    for raw in text.split("\n"):
        current = ""
        for word in raw.split():
            probe = f"{current} {word}".strip()
            if current and pymupdf.get_text_length(probe, fontname=font, fontsize=size) > width:
                lines.append(current)
                current = word
            else:
                current = probe
        lines.append(current)
    return [line for line in lines if line]


def _block_height(text: str, width: float, size: float, bold: bool = False) -> float:
    return len(_wrap(text, width, size, bold)) * (size * 1.32)


def _text(page: pymupdf.Page, rect: pymupdf.Rect, text: str, size: float, bold: bool = False) -> float:
    """Draw wrapped text line by line and return the y of the next free line."""
    font = "hebo" if bold else "helv"
    y = rect.y0 + size
    for line in _wrap(text, rect.width, size, bold):
        page.insert_text((rect.x0, y), line, fontsize=size, fontname=font)
        y += size * 1.32
    return y


def _running_head(page: pymupdf.Page, paper: SyntheticPaper, number: int) -> None:
    _text(
        page,
        pymupdf.Rect(MARGIN, 24, PAGE_WIDTH - MARGIN, 44),
        f"{paper.author_names[0].split()[-1]} et al. / {paper.journal} {paper.volume} ({paper.year}) {paper.pages}",
        SMALL_SIZE,
    )
    _text(
        page,
        pymupdf.Rect(MARGIN, PAGE_HEIGHT - 44, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 24),
        f"{paper.journal} | https://doi.org/{paper.doi} | {paper.year} | {number}",
        SMALL_SIZE,
    )


def _cover_page(document: pymupdf.Document, paper: SyntheticPaper) -> None:
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    _text(page, pymupdf.Rect(MARGIN, 60, PAGE_WIDTH - MARGIN, 100), "Northfield Research Online", 11)
    _text(
        page,
        pymupdf.Rect(MARGIN, 120, PAGE_WIDTH - MARGIN, 180),
        "This is a repository copy of the published version.\n"
        "Research online URL for this paper: https://eprints.northfield.ac.uk/id/eprint/90210/",
        11,
    )
    _text(page, pymupdf.Rect(MARGIN, 200, PAGE_WIDTH - MARGIN, 220), "Version: Published Version", 11)
    _text(
        page,
        pymupdf.Rect(MARGIN, 240, PAGE_WIDTH - MARGIN, 320),
        f"Article:\n{', '.join(paper.author_names)} ({paper.year}) {paper.title}. "
        f"{paper.journal}. pp. {paper.pages}. ISSN: 2049-1115",
        11,
    )
    _text(page, pymupdf.Rect(MARGIN, 340, PAGE_WIDTH - MARGIN, 360), f"https://doi.org/{paper.doi}", 11)
    _text(
        page,
        pymupdf.Rect(MARGIN, 600, PAGE_WIDTH - MARGIN, 680),
        "Reuse\nThis article is distributed under the terms of the Creative Commons Attribution (CC BY) licence.",
        SMALL_SIZE,
    )


def _front_page(document: pymupdf.Document, paper: SyntheticPaper, number: int) -> None:
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    _running_head(page, paper, number)
    width = PAGE_WIDTH - 2 * MARGIN
    full = pymupdf.Rect(MARGIN, 0, PAGE_WIDTH - MARGIN, PAGE_HEIGHT)

    def draw(cursor: float, text: str, size: float, bold: bool = False, gap: float = 8.0) -> float:
        rect = pymupdf.Rect(full.x0, cursor, full.x1, PAGE_HEIGHT)
        return _text(page, rect, text, size, bold) + gap

    cursor = 62.0
    cursor = draw(cursor, paper.article_type, BODY_SIZE, True, 6.0)
    cursor = draw(cursor, paper.title, TITLE_SIZE, True, 12.0)
    cursor = draw(cursor, paper.authors, 11.0, False, 10.0)
    cursor = draw(cursor, "\n".join(paper.affiliations), SMALL_SIZE, False, 8.0)
    for note in paper.notes:
        cursor = draw(cursor, note, SMALL_SIZE, False, 2.0)
    cursor += 6
    for label in (paper.received, paper.accepted, paper.published):
        cursor = draw(cursor, label, SMALL_SIZE, False, 2.0)
    cursor += 10
    cursor = draw(cursor, "Abstract", HEADING_SIZE, True, 6.0)
    for heading, body in paper.abstract:
        cursor = draw(cursor, heading, BODY_SIZE, True, 3.0)
        cursor = draw(cursor, body, 9.5, False, 8.0)
    draw(cursor, paper.keywords, SMALL_SIZE, False, 0.0)
    del width


def _column_rects(top: float) -> tuple[pymupdf.Rect, pymupdf.Rect]:
    bottom = PAGE_HEIGHT - 56
    left = pymupdf.Rect(MARGIN, top, MARGIN + COLUMN_WIDTH, bottom)
    right = pymupdf.Rect(MARGIN + COLUMN_WIDTH + GUTTER, top, PAGE_WIDTH - MARGIN, bottom)
    return left, right


def _body_pages(document: pymupdf.Document, paper: SyntheticPaper, start_number: int) -> int:
    blocks: list[tuple[str, str]] = []
    for heading, paragraphs in paper.sections:
        blocks.append(("heading", heading))
        for paragraph in paragraphs:
            blocks.append(("body", paragraph))
    blocks.append(("heading", "References"))
    for reference in paper.references:
        blocks.append(("small", reference))

    number = start_number
    index = 0
    while index < len(blocks):
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        _running_head(page, paper, number)
        for rect in _column_rects(60.0):
            cursor = rect.y0
            while index < len(blocks):
                kind, text = blocks[index]
                size = HEADING_SIZE if kind == "heading" else (SMALL_SIZE if kind == "small" else BODY_SIZE)
                bold = kind == "heading"
                height = _block_height(text, rect.width, size, bold)
                if cursor > rect.y0 and cursor + height > rect.y1:
                    break
                cursor = _text(page, pymupdf.Rect(rect.x0, cursor, rect.x1, rect.y1), text, size, bold) + 9.0
                index += 1
                if cursor > rect.y1 - size:
                    break
        number += 1
    return number


def _table_page(document: pymupdf.Document, paper: SyntheticPaper, number: int) -> None:
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    _running_head(page, paper, number)
    cursor = 70.0
    cursor = (
        _text(page, pymupdf.Rect(MARGIN, cursor, PAGE_WIDTH - MARGIN, PAGE_HEIGHT), paper.table_caption, SMALL_SIZE) + 8
    )
    for row in paper.table_rows:
        cursor = _text(page, pymupdf.Rect(MARGIN, cursor, PAGE_WIDTH - MARGIN, PAGE_HEIGHT), row, SMALL_SIZE) + 4


def build_pdf(path: Path, paper: SyntheticPaper | None = None) -> Path:
    paper = paper or SyntheticPaper()
    document = pymupdf.open()
    number = 1
    if paper.cover_sheet:
        _cover_page(document, paper)
        number += 1
    _front_page(document, paper, number)
    number += 1
    number = _body_pages(document, paper, number)
    if paper.include_table:
        _table_page(document, paper, number)
    document.set_metadata({"title": paper.title, "author": ", ".join(paper.author_names)})
    document.save(path)
    document.close()
    return path
