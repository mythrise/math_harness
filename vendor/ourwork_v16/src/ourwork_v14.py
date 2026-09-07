from __future__ import annotations
import json,subprocess
from pathlib import Path
from typing import Any,Dict
import ourwork_v3 as base
from reference_editable_v12 import render_reference_editable,inventory_for_template,semantic_slot_inventory
from semantic_geometry_v12 import apply_semantic_geometry
from image_slots_v14 import apply_image_slots,list_image_slots,image_placement_report
from config_validator_v14 import lint_config
from output_guard_v14 import validate_output


def render(template_id:str,config:Dict[str,Any]|None=None,mode='auto',exact_reference=False,strict=False,guard=True):
    config=config or {}
    if mode in ('reference_editable','reference_semantic','reference_semantic_image'):
        lint=lint_config(template_id,config)
        if strict and not lint['ok']:raise ValueError('; '.join(lint['errors']))
        out=render_reference_editable(template_id,config)
        if mode in ('reference_semantic','reference_semantic_image'):out=apply_semantic_geometry(template_id,out,config)
        if mode in ('reference_editable','reference_semantic','reference_semantic_image'):out=apply_image_slots(template_id,out,config)
        if guard:
            report=validate_output(template_id,out,config)
            if not report['ok']:raise RuntimeError('; '.join(report['errors']))
        return out
    return base.render(template_id,config,mode=mode,exact_reference=exact_reference)


def save(template_id,out,config=None,mode='reference_semantic_image',exact_reference=False,strict=False,guard=True):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(render(template_id,config or {},mode,exact_reference,strict,guard),encoding='utf-8');return out


def export_inkscape(svg_path,png_path=None,pdf_path=None):
    svg_path=Path(svg_path)
    if png_path:
        png_path=Path(png_path);png_path.parent.mkdir(parents=True,exist_ok=True);subprocess.run(['inkscape',str(svg_path),'--export-type=png',f'--export-filename={png_path}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if pdf_path:
        pdf_path=Path(pdf_path);pdf_path.parent.mkdir(parents=True,exist_ok=True);subprocess.run(['inkscape',str(svg_path),'--export-type=pdf',f'--export-filename={pdf_path}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--template',required=True);ap.add_argument('--config');ap.add_argument('--mode',default='reference_semantic_image',choices=['auto','reference','reference_editable','reference_semantic','reference_semantic_image']);ap.add_argument('--out');ap.add_argument('--png');ap.add_argument('--pdf');ap.add_argument('--inventory-out');ap.add_argument('--slots-out');ap.add_argument('--image-slots-out');ap.add_argument('--placement-report-out');ap.add_argument('--lint-out');ap.add_argument('--validate-out');ap.add_argument('--strict',action='store_true');ap.add_argument('--no-guard',action='store_true');ap.add_argument('--exact-reference',action='store_true')
 a=ap.parse_args();cfg=json.loads(Path(a.config).read_text(encoding='utf-8')) if a.config else {};lint=lint_config(a.template,cfg)
 if a.inventory_out:Path(a.inventory_out).write_text(json.dumps(inventory_for_template(a.template),ensure_ascii=False,indent=2),encoding='utf-8')
 if a.slots_out:Path(a.slots_out).write_text(json.dumps(semantic_slot_inventory(a.template),ensure_ascii=False,indent=2),encoding='utf-8')
 if a.image_slots_out:Path(a.image_slots_out).write_text(json.dumps(list_image_slots(a.template),ensure_ascii=False,indent=2),encoding='utf-8')
 if a.placement_report_out:Path(a.placement_report_out).write_text(json.dumps(image_placement_report(a.template,cfg),ensure_ascii=False,indent=2),encoding='utf-8')
 if a.lint_out:Path(a.lint_out).write_text(json.dumps(lint,ensure_ascii=False,indent=2),encoding='utf-8')
 if a.strict and not lint['ok']:raise SystemExit('Config validation failed: '+'; '.join(lint['errors']))
 if a.out:
  svg=save(a.template,a.out,cfg,a.mode,a.exact_reference,a.strict,not a.no_guard);export_inkscape(svg,a.png,a.pdf)
  if a.validate_out:Path(a.validate_out).write_text(json.dumps(validate_output(a.template,Path(svg).read_text(encoding='utf-8'),cfg),ensure_ascii=False,indent=2),encoding='utf-8')
