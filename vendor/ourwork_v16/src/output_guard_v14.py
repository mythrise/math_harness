from __future__ import annotations
import re
from typing import Any, Dict
from lxml import etree
from reference_editable_v12 import image_data_hashes, reference_svg_path


def validate_output(template_id:str,output:str,config:Dict[str,Any]|None=None)->Dict[str,Any]:
    config=config or {};errors=[];warnings=[]
    try:etree.fromstring(output.encode('utf-8'),parser=etree.XMLParser(huge_tree=True,recover=False));xml_ok=True
    except Exception as e:xml_ok=False;errors.append(f'Invalid SVG XML: {e}')
    ref=reference_svg_path(template_id).read_text(encoding='utf-8');ref_hash=image_data_hashes(ref);out_hash=image_data_hashes(output)
    added_images=bool(config.get('images'));pathized_edit=template_id in ('T16_radial_bubble','T17_cube_ray') and bool((config.get('slots') or config.get('slot_groups')))
    allow_image_mutation=added_images or pathized_edit
    if not allow_image_mutation:
        images_preserved=(ref_hash==out_hash)
        if not images_preserved:errors.append('Embedded image payload/hash changed unexpectedly')
    else:
        # v14 overlays new images; every original embedded image payload must still be present byte-equivalently.
        images_preserved=all(h in out_hash for h in ref_hash)
        if not images_preserved and not pathized_edit:errors.append('Original embedded images were removed or altered unexpectedly')
    external=re.findall(r'(?:href|xlink:href)="(?!data:)([^"]+)"',output,re.I)
    if external:warnings.append(f'External hrefs present: {len(external)}')
    image_layer='image-slots-v14' in output if added_images else False
    if added_images and not image_layer:errors.append('images were configured but image-slots-v14 layer is missing')
    return {'template_id':template_id,'ok':not errors,'xml_ok':xml_ok,'images_preserved':images_preserved,'allow_image_mutation':allow_image_mutation,'image_layer_present':image_layer,'errors':errors,'warnings':warnings}
