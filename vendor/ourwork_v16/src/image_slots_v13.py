from __future__ import annotations
import base64, hashlib, json, mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def _registry() -> Dict[str, Any]:
    p = ROOT / 'registry' / 'image_slots_v13.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}


def list_image_slots(template_id: str) -> Dict[str, Any]:
    reg = _registry()
    item = reg.get(template_id, {})
    return {
        'template_id': template_id,
        'image_slots': item.get('image_slots', []),
    }


def _mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or 'image/png'


def _resolve_path(path_like: str | Path) -> Path:
    p = Path(path_like)
    if p.exists():
        return p
    alt = (ROOT / p).resolve()
    return alt


def _data_uri(path: Path) -> str:
    raw = path.read_bytes()
    return f"data:{_mime_for(path)};base64,{base64.b64encode(raw).decode('ascii')}"


def _image_size(path: Path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return int(im.width), int(im.height)


def _safe_id(prefix: str, slot_name: str, img_path: str) -> str:
    h = hashlib.sha1((slot_name + '|' + img_path).encode('utf-8')).hexdigest()[:10]
    return f'{prefix}-{slot_name}-{h}'


def _parse_align(value: str | None) -> Tuple[float, float]:
    ax = ay = 0.5
    v = (value or 'center').lower().strip()
    table = {
        'center': (0.5, 0.5), 'middle': (0.5, 0.5),
        'left': (0.0, 0.5), 'right': (1.0, 0.5),
        'top': (0.5, 0.0), 'bottom': (0.5, 1.0),
        'top-left': (0.0, 0.0), 'left-top': (0.0, 0.0),
        'top-right': (1.0, 0.0), 'right-top': (1.0, 0.0),
        'bottom-left': (0.0, 1.0), 'left-bottom': (0.0, 1.0),
        'bottom-right': (1.0, 1.0), 'right-bottom': (1.0, 1.0),
    }
    return table.get(v, (ax, ay))


def _placement(slot: Dict[str, Any], iw: float, ih: float, spec: Dict[str, Any]) -> Tuple[float, float, float, float, float, float, float, float]:
    pad = float(spec.get('padding', slot.get('padding', 0)) or 0)
    x = float(slot['x']) + pad
    y = float(slot['y']) + pad
    w = max(1.0, float(slot['width']) - 2 * pad)
    h = max(1.0, float(slot['height']) - 2 * pad)
    fit = str(spec.get('fit', slot.get('fit', 'cover'))).lower().strip()
    if fit == 'stretch':
        return x, y, w, h, x, y, w, h

    if fit == 'contain':
        scale = min(w / iw, h / ih)
    else:  # cover / auto
        scale = max(w / iw, h / ih)
    rw, rh = iw * scale, ih * scale

    focus_x = spec.get('focus_x', slot.get('focus_x'))
    focus_y = spec.get('focus_y', slot.get('focus_y'))
    if focus_x is None or focus_y is None:
        ax, ay = _parse_align(spec.get('align', slot.get('align')))
        focus_x = ax if focus_x is None else float(focus_x)
        focus_y = ay if focus_y is None else float(focus_y)
    else:
        focus_x = float(focus_x)
        focus_y = float(focus_y)
    focus_x = max(0.0, min(1.0, focus_x))
    focus_y = max(0.0, min(1.0, focus_y))

    if fit == 'contain':
        rx = x + (w - rw) * focus_x
        ry = y + (h - rh) * focus_y
    else:  # cover
        rx = x - (rw - w) * focus_x
        ry = y - (rh - h) * focus_y
    return x, y, w, h, rx, ry, rw, rh


def _clip_fragment(clip_id: str, slot: Dict[str, Any], clip_x: float, clip_y: float, clip_w: float, clip_h: float) -> str:
    clip = slot.get('clip', 'rect')
    rx = float(slot.get('radius', slot.get('rx', 0)) or 0)
    if clip == 'rounded_rect' or rx > 0:
        return f'<clipPath id="{clip_id}"><rect x="{clip_x:.3f}" y="{clip_y:.3f}" width="{clip_w:.3f}" height="{clip_h:.3f}" rx="{rx:.3f}" ry="{rx:.3f}"/></clipPath>'
    return f'<clipPath id="{clip_id}"><rect x="{clip_x:.3f}" y="{clip_y:.3f}" width="{clip_w:.3f}" height="{clip_h:.3f}"/></clipPath>'


def _image_fragment(template_id: str, slot: Dict[str, Any], spec: Dict[str, Any]) -> str:
    path = _resolve_path(spec['path'])
    if not path.exists():
        raise FileNotFoundError(f'image path not found for slot {slot["name"]}: {path}')
    iw, ih = _image_size(path)
    clip_x, clip_y, clip_w, clip_h, rx, ry, rw, rh = _placement(slot, iw, ih, spec)
    clip_id = _safe_id(f'{template_id}-clip', slot['name'], str(path))
    img_id = _safe_id(f'{template_id}-img', slot['name'], str(path))
    href = _data_uri(path)
    opacity = float(spec.get('opacity', 1.0))
    defs = _clip_fragment(clip_id, slot, clip_x, clip_y, clip_w, clip_h)
    img = (
        f'<image id="{img_id}" x="{rx:.3f}" y="{ry:.3f}" width="{rw:.3f}" height="{rh:.3f}" '
        f'preserveAspectRatio="none" clip-path="url(#{clip_id})" opacity="{opacity:.4f}" '
        f'xlink:href="{href}" href="{href}"/>'
    )
    border = ''
    if slot.get('stroke') or slot.get('stroke_width'):
        stroke = slot.get('stroke', '#ffffff')
        sw = float(slot.get('stroke_width', 1.0) or 1.0)
        rad = float(slot.get('radius', slot.get('rx', 0)) or 0)
        border = f'<rect x="{clip_x:.3f}" y="{clip_y:.3f}" width="{clip_w:.3f}" height="{clip_h:.3f}" rx="{rad:.3f}" ry="{rad:.3f}" fill="none" stroke="{stroke}" stroke-width="{sw:.3f}"/>'
    return defs + img + border


def apply_image_slots(template_id: str, source: str, config: Dict[str, Any] | None = None) -> str:
    config = config or {}
    images = config.get('images') or {}
    if not images:
        return source
    reg = _registry().get(template_id, {})
    slots = reg.get('image_slots', [])
    slot_map = {s['name']: s for s in slots}
    fragments: List[str] = []
    defs: List[str] = []
    body: List[str] = []
    for name, spec in images.items():
        if name not in slot_map:
            continue
        frag = _image_fragment(template_id, slot_map[name], spec)
        # split defs/others because clipPath must live in <defs>
        # simple split: first clipPath chunk then the rest
        pos = frag.find('</clipPath>')
        if pos >= 0:
            defs.append(frag[:pos+11])
            body.append(frag[pos+11:])
        else:
            body.append(frag)
    if not defs and not body:
        return source
    layer = ''
    if defs:
        layer += '<defs>' + ''.join(defs) + '</defs>'
    layer += '<g id="image-slots-v13">' + ''.join(body) + '</g>'
    idx = source.lower().rfind('</svg>')
    if idx < 0:
        raise ValueError('Malformed SVG: closing </svg> not found')
    return source[:idx] + layer + source[idx:]
