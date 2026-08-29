"""Byline and publisher-citation parsing."""

from __future__ import annotations

from paper_digest.authors import (
    parse_byline,
    roles_from_notes,
    split_byline,
    strip_byline_markup,
)
from paper_digest.citation import journal_from_running_heads, parse_citation


def test_superscript_affiliation_keys_are_stripped_but_particles_survive():
    byline = (
        "Matthew J. Page a , ∗, Joanne E. McKenzie a , Larissa Shamseer f , g , "
        "Elizabeth W. Loder w , x , Evan Mayo-Wilson y , Susan van den Hof, Jan de Vries, David Moher ah , ai"
    )
    names, groups, truncated = split_byline(byline)
    assert names == [
        "Matthew J. Page",
        "Joanne E. McKenzie",
        "Larissa Shamseer",
        "Elizabeth W. Loder",
        "Evan Mayo-Wilson",
        "Susan van den Hof",
        "Jan de Vries",
        "David Moher",
    ]
    assert groups == []
    assert truncated is False


def test_orcid_icon_glyph_and_contribution_symbols_are_removed():
    byline = (
        "Ineke SpruijtID1☯*, Connie ErkensID1☯, Jeanine Suurmond2☯, Erik Huisman3‡, "
        "Frank CobelensID7☯, Susan van den Hof1☯¤"
    )
    names, _groups, _truncated = split_byline(byline)
    assert names == [
        "Ineke Spruijt",
        "Connie Erkens",
        "Jeanine Suurmond",
        "Erik Huisman",
        "Frank Cobelens",
        "Susan van den Hof",
    ]


def test_footnote_roles_are_attributed_through_byline_markers():
    authors, _groups, _truncated = parse_byline(
        "Ineke SpruijtID1☯*, Connie ErkensID1☯, Erik Huisman3‡, Susan van den Hof1☯¤"
    )
    roles = roles_from_notes(
        authors,
        "☯ These authors contributed equally to this work.\n‡ These authors also contributed equally to this work.",
    )
    assert roles["equal"] == ["Ineke Spruijt", "Connie Erkens", "Susan van den Hof", "Erik Huisman"]


def test_truncated_bylines_are_reported():
    names, _groups, truncated = split_byline("Ana Silva, Bo Chen, Cara Diaz et al.")
    assert names == ["Ana Silva", "Bo Chen", "Cara Diaz"]
    assert truncated is True


def test_strip_markup_leaves_a_bare_name_untouched():
    assert strip_byline_markup("Rafael de Souza") == "Rafael de Souza"


def test_repository_cover_citation_yields_title_journal_and_pages():
    parsed = parse_citation(
        "Page, Matthew J, McKenzie, Joanne E, Bossuyt, Patrick M et al. (2021) "
        "The PRISMA 2020 statement: An updated guideline for reporting systematic reviews. "
        "Journal of Clinical Epidemiology. pp. 178-189. ISSN: 0895-4356"
    )
    assert parsed.year == 2021
    assert parsed.title == "The PRISMA 2020 statement: An updated guideline for reporting systematic reviews"
    assert parsed.journal == "Journal of Clinical Epidemiology"
    assert parsed.pages == "178-189"
    assert parsed.issn == "0895-4356"
    assert parsed.authors[:2] == ["Matthew J Page", "Joanne E McKenzie"]
    assert parsed.truncated_authors is True


def test_publisher_citation_yields_volume_issue_article_number_and_doi():
    parsed = parse_citation(
        "Spruijt I, Erkens C, Suurmond J, et al. (2019) Implementation of latent tuberculosis infection "
        "screening and treatment among newly arriving immigrants in the Netherlands: A mixed methods pilot "
        "evaluation. PLoS ONE 14(7): e0219252. https://doi.org/10.1371/journal.pone.0219252"
    )
    assert (parsed.year, parsed.volume, parsed.issue) == (2019, "14", "7")
    assert parsed.article_number == "e0219252"
    assert parsed.journal == "PLoS ONE"
    assert parsed.doi == "10.1371/journal.pone.0219252"


def test_comma_delimited_cite_this_article_form_does_not_invent_a_year():
    parsed = parse_citation(
        "M.J. Page et al., The PRISMA 2020 statement: An updated guideline for reporting systematic "
        "reviews, Journal of Clinical Epidemiology, https://doi.org/10.1016/j.jclinepi.2021.03.001"
    )
    assert parsed.year is None
    assert parsed.journal == "Journal of Clinical Epidemiology"
    assert parsed.title.startswith("The PRISMA 2020 statement")


def test_journal_name_is_recovered_from_either_running_head_style():
    assert (
        journal_from_running_heads(["2 M.J. Page et al. / Journal of Clinical Epidemiology xxx (xxxx) xxx"])
        == "Journal of Clinical Epidemiology"
    )
    assert (
        journal_from_running_heads(["PLOS ONE | https://doi.org/10.1371/journal.pone.0219252 July 1, 2019 1 / 17"])
        == "PLOS ONE"
    )


def test_journal_is_recovered_from_the_volume_locator_when_no_period_separates_it():
    parsed = parse_citation(
        "Son H, Song S & Rhee J C (2007) Histopathology 51, 105-110 "
        "Prognostic indicators of gastric carcinoma confined to the muscularis propria."
    )
    assert parsed.journal == "Histopathology"
    assert parsed.title == "Prognostic indicators of gastric carcinoma confined to the muscularis propria"
    assert parsed.authors == ["Son H", "Song S", "Rhee J C"]


def test_a_copyright_line_is_never_read_as_the_journal():
    parsed = parse_citation(
        "© 2007 The Authors. Journal compilation Blackwell Publishing Ltd Histopathology 51, 105-110."
    )
    assert "Blackwell" not in parsed.journal
    assert "Authors" not in parsed.journal
