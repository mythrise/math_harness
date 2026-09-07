# Auto Image System v16 Architecture

## 1. Native PPTX discovery

`pptx_image_slot_discovery_v14.py` walks PowerPoint XML recursively.

For a group transform:

```text
child coordinate
  -> chOff/chExt normalization
  -> group off/ext scaling
  -> parent group transform
  -> slide coordinate
  -> 960 x 540 SVG coordinate
```

It recognizes:

- `<p:pic>` native Picture
- `<p:sp>` with `<a:blipFill>` image-filled shapes

The latter is important because T01's rounded input/output photos are not Picture objects; they are rounded rectangle shapes filled by images.

## 2. Caption region discovery

`caption_region_discovery_v15.py` finds caption text such as:

```text
(a) Coupling Analysis Model
(b) Rasterization of MMNR Area
```

It then finds the smallest enclosing stage panel and infers a visual region immediately above the caption.

This is how T02 image panels are discovered even though they are not native Picture placeholders.

## 3. Image assignment

Two modes:

- `reading_order`: top-to-bottom, left-to-right
- `aspect`: greedy aspect-ratio matching

Explicit `images` always overrides automatic assignment.

## 4. Fitting

- photo -> `cover` by default
- figure/content panel -> `contain` by default
- icon -> `contain`

Manual overrides remain available.

## 5. Smart trim

Large white/transparent margins are removed before fitting. This is especially useful for paper plots and screenshots.

## 6. Smart focus

For a photo in `cover` mode without manual focus, v16 computes a lightweight deterministic saliency centroid from edge/contrast energy.

This is deliberately not an object detector. It has no model dependency and remains reproducible.

## 7. Embedding

Images are downsampled to a print-appropriate size based on their actual SVG display dimensions, then embedded as data URIs. This prevents a tiny 80-pixel placeholder from adding a 30 MB original photo to the SVG.

## 8. Safety

The original Reference SVG is not destructively rewritten. New image layers cover the relevant region while output guards verify that original embedded image payloads remain present and XML remains valid.
