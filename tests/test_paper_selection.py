from pathlib import Path
import pytest
from cumcm_harness.paper import render_pages
from cumcm_harness.common import IntegrityError

def test_render_only_requested_pages(tmp_path):
    import fitz
    doc=fitz.open()
    for _ in range(8):doc.new_page()
    pdf=tmp_path/'source.pdf';doc.save(pdf);doc.close()
    paths=render_pages(pdf,tmp_path/'selected',page_indices=[0,1,7,7])
    assert [p.name for p in paths]==['page-001.png','page-002.png','page-008.png']
    with pytest.raises(IntegrityError):render_pages(pdf,tmp_path/'bad',page_indices=[100])
