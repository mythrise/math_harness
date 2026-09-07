from __future__ import annotations
import re
from typing import Any,Dict
from lxml import etree
from reference_editable_v12 import image_data_hashes,reference_svg_path

def validate_output(template_id:str,output:str,config:Dict[str,Any]|None=None)->Dict[str,Any]:
 config=config or {};errors=[];warnings=[]
 try:etree.fromstring(output.encode('utf-8'),parser=etree.XMLParser(huge_tree=True,recover=False));xml_ok=True
 except Exception as e:xml_ok=False;errors.append(f'Invalid SVG XML: {e}')
 ref=reference_svg_path(template_id).read_text(encoding='utf-8');rh=image_data_hashes(ref);oh=image_data_hashes(output);added=bool(config.get('images') or config.get('auto_images'));pathized=template_id in ('T16_radial_bubble','T17_cube_ray') and bool((config.get('slots') or config.get('slot_groups')))
 allow=added or pathized
 if not allow:
  preserved=rh==oh
  if not preserved:errors.append('Embedded image payload/hash changed unexpectedly')
 else:
  preserved=all(h in oh for h in rh)
  if not preserved and not pathized:errors.append('Original embedded images were removed or altered unexpectedly')
 external=re.findall(r'(?:href|xlink:href)="(?!data:)([^"]+)"',output,re.I)
 if external:warnings.append(f'External hrefs present: {len(external)}')
 layer='image-slots-v16' in output if added else False
 if added and not layer:errors.append('images were configured but image-slots-v16 layer is missing')
 return {'template_id':template_id,'ok':not errors,'xml_ok':xml_ok,'images_preserved':preserved,'image_layer_present':layer,'errors':errors,'warnings':warnings}
