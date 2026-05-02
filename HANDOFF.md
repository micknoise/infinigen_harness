# Handoff Notes

## Summary

This session focused on scene placement bugs between Blender export and A-Frame assembly.

The current codebase keeps the transform/export fixes that made the room geometry coherent and removes duplicated helper geometry from the scene. The last attempted portal-scaling change was reverted.

## Changes that remain in place

### 1. GLB export is now local-space instead of double-applying transforms

File: `scripts/export_gltf.py`

- Added a temporary export copy path for each object.
- The export copy is detached from its Blender parent hierarchy.
- The export copy is reset to identity before glTF export.
- The manifest remains the source of truth for world-space placement in A-Frame.

This fixed the earlier issue where objects appeared randomly offset because both the GLB and the manifest were carrying placement transforms.

### 2. Export filtering now skips helper geometry

File: `scripts/export_gltf.py`

Added `should_export_object(obj)` and used collection names to exclude non-scene helper meshes:

- `placeholders:*`
- collections containing `base_elements`

This removed:

- portal cutter cuboids such as `door*`, `window*`, `entrance`
- reusable source meshes such as `Cube*`, `Plane*`, `BézierCurve*`
- room placeholder shells and room placeholder meshes

The result is that the exported scene now contains the visible room surfaces and the visible door/window factory instances, rather than overlapping helper geometry.

### 3. Resume support was added to the exporter

File: `scripts/export_gltf.py`

Added:

- `--start-index`
- `--skip-manifest`

This was introduced because the Blender/Python export process was intermittently crashing near shutdown, which made it useful to resume only the unfinished tail of the object list without overwriting a good manifest.

## Change that was reverted

### Portal scaling attempt

I tried scaling `PanelDoorFactory(...)` and `WindowFactory(...)` objects to match their parent aperture sizes. That change is **not** retained.

What was attempted:

- measured door/window factory mesh bounds against their parent portal cutter dimensions
- applied a fitted uniform scale in the manifest

Why it was reverted:

- it was not the requested fix
- it changed portal appearance instead of addressing the root asset/layout problem

Current state after revert:

- portal object scales in `outputs/7412/manifest.json` are back to `[1.0, 1.0, 1.0]`

## Findings from investigation

### Root cause of the original placement bug

The first major placement bug came from exporting GLBs with transforms that overlapped with the transforms written into `manifest.json`. A-Frame then effectively positioned objects twice.

### Why the scene later glitched

The `.blend` contains helper collections and placeholder portal geometry that should not be exported as visible objects. Examples observed:

- `placeholders:portal_cutters`
- `placeholders:room_shells`
- `placeholders:room_meshes`
- `door_base_elements`
- `door_base_elements.*`

Those collections contained blocking cuboids and source meshes that caused z-fighting and duplicated geometry in the browser.

### Remaining unresolved issue

Doors and windows are still exported from `unique_assets:doors` and `unique_assets:windows` as raw factory instances parented to portal cutter placeholders.

Observed behavior:

- doors can appear visually too large for their apertures
- some windows/doors appear mismatched against the openings they theoretically belong to

Likely next investigation areas:

1. Determine whether the correct visual asset should be exported from each portal family at all.
2. Check whether the factory mesh is intended to be interpreted relative to the parent cutter, a different parent, or a hidden reference transform.
3. Check whether the cutter object represents a boolean aperture only, while the visible asset requires an additional offset/hierarchy rule that is not currently applied.
4. Inspect whether some portal assets are authored as multi-panel/double-door assemblies by design, even when attached to a single-width opening.

## Commands used during debugging

Representative commands used during this session:

```bash
bash ./scripts/export.sh --blend outputs/7412/coarse/scene.blend --output outputs/7412 --texture-resolution 512 --decimate-ratio 0.4 --seed 7412 --room-type Kitchen
python3 scripts/build_aframe.py --manifest outputs/7412/manifest.json --template templates/aframe.html.j2 --output outputs/7412/index.html
python3 -m http.server 8000 --bind 127.0.0.1 --directory outputs/7412
```

## Files changed in this session

- `scripts/export_gltf.py`
- `outputs/7412/manifest.json`
- `outputs/7412/index.html`

## Current preview URL

If the local server is still running:

`http://127.0.0.1:8000/index.html`
