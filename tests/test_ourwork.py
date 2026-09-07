"""Byte-identical no-op checks against all twenty original reference templates."""
import pytest
from cumcm_harness.common import ROOT,read_json,verify_vendor
from cumcm_harness.figures import ourwork
IDS=[t['id'] for t in read_json(ROOT/'vendor/ourwork_v16/registry/templates.json')]
@pytest.mark.parametrize('template',IDS)
def test_reference_noop(template):
    runtime=ourwork()
    from reference_editable_v12 import reference_svg_path
    source=reference_svg_path(template).read_text('utf-8')
    assert runtime.render(template,{},mode='reference_semantic_image',strict=True,guard=True)==source

def test_vendor_unchanged():assert verify_vendor()['files']==408
