import shutil

import pymupdf
import pytest
from paper_digest.parsers.pdf import extract_pdf
from paper_digest.text import normalize_prose


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_scanned_page_uses_deterministic_ocr(tmp_path):
    source = pymupdf.open()
    page = source.new_page(width=595, height=842)
    sentence = (
        "Synthetic document extraction validation uses a fixed optical character recognition path. "
        "The measured outcome is reproducible and no language model participates in this test."
    )
    page.insert_textbox(pymupdf.Rect(55, 70, 540, 250), sentence, fontsize=16)
    pixels = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    source.close()

    scanned = pymupdf.open()
    scanned_page = scanned.new_page(width=595, height=842)
    scanned_page.insert_image(scanned_page.rect, stream=pixels.tobytes("png"))
    path = tmp_path / "synthetic-scan.pdf"
    scanned.save(path)
    scanned.close()

    extraction = extract_pdf(path, enable_ocr=True)
    assert extraction.ocr_pages == [1]
    assert "optical character recognition" in normalize_prose(extraction.full_text).casefold()
    assert "tesseract-ocr" in extraction.extractor
