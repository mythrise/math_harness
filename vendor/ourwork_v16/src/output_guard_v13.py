from __future__ import annotations
import re
from typing import Any, Dict
from lxml import etree
from reference_editable_v12 import image_data_hashes, reference_svg_path


def validate_output(template_id:str, output:str, config:Dict[str,Any]|None=None) -> Dict[str,Any]:
    config=config or {}
    errors=[];warnings=[]
    try:
        etree.fromstring(output.encode('utf-8'),parser=etree.XMLParser(huge_tree=True,recover=False))
        xml_ok=True
    except Exception as e:
        xml_ok=False;errors.append(f'Invalid SVG XML: {e}')
    ref=reference_svg_path(template_id).read_text(encoding='utf-8')
    ref_hash=image_data_hashes(ref); out_hash=image_data_hashes(output)
    allow_image_mutation = bool(config.get('images')) or (template_id in ('T16_radial_bubble','T17_cube_ray') and bool((config.get('slots') or config.get('slot_groups'))))
    if not allow_image_mutation:
        images_preserved=(ref_hash==out_hash)
        if not images_preserved:
            errors.append('Embedded image payload/hash changed unexpectedly')
    else:
        images_preserved=all(h in out_hash for h in ref_hash)
        if not images_preserved:
            errors.append('Original embedded images were removed or altered unexpectedly')
    external=re.findall(r'(?:href|xlink:href)="(?!data:)([^"]+)"',output,re.I)
    if external:
        warnings.append(f'External hrefs present: {len(external)}')
    return {'template_id':template_id,'ok':not errors,'xml_ok':xml_ok,'images_preserved':images_preserved,'allow_image_mutation':allow_image_mutation,'errors':errors,'warnings':warnings}
