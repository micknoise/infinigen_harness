# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

This harness bridges **Infinigen** (procedural 3D scene generation) and **A-Frame** (WebXR), converting a JSON scene config into an interactive 3D browser scene. The full workflow is documented in `AGENT_GUIDE.md` — read it before making changes.

## Pipeline commands

```bash
# Full pipeline: Infinigen → Blender export → A-Frame HTML
./scripts/generate.sh --config configs/scene_config.json

# Partial pipeline flags
./scripts/generate.sh --config configs/scene_config.json --skip-export   # reuse existing .blend
./scripts/generate.sh --config configs/scene_config.json --skip-aframe   # stop after export
./scripts/generate.sh --config configs/scene_config.json --export-only   # skip Infinigen generation

# Re-export with different settings (no re-generation)
./scripts/export.sh --blend outputs/42/coarse/scene.blend --output outputs/42 --texture-resolution 512

# Stage 3 only (useful for testing without Infinigen/Blender)
python3 scripts/build_aframe.py --manifest outputs/42/manifest.json --template templates/aframe.html.j2 --output outputs/42/index.html

# View the generated scene
python3 -m http.server 8000 --directory outputs/42
```

There is no build step, test suite, or linter. The harness is script-based.

## Three-stage architecture

```
scene_config.json
      ↓
[Stage 1] generate.sh → python -m infinigen_examples.generate_indoors
      → outputs/{seed}/coarse/scene.blend

[Stage 2] blender --background --python export_gltf.py
      → outputs/{seed}/objects/*.glb  (per-object, baked textures)
      → outputs/{seed}/manifest.json

[Stage 3] python build_aframe.py
      → outputs/{seed}/index.html
```

Each stage consumes the previous stage's output. Stages can be run independently using the flags above.

## Directory layout

```
scripts/          generate.sh, export.sh, export_gltf.py, build_aframe.py
templates/        aframe.html.j2
configs/          scene_config.json, room_types.json, demo_kitchen.json
outputs/{seed}/   manifest.json, index.html, objects/*.glb
```

## Key files and their roles

| File | Role |
|------|------|
| `scripts/generate.sh` | Orchestrator: parses config, calls all three stages |
| `scripts/export_gltf.py` | **Runs inside Blender's Python** — bakes PBR textures, decimates geometry, exports per-object .glb, writes manifest.json |
| `scripts/build_aframe.py` | Reads manifest.json, renders index.html via Jinja2 template (with built-in fallback) |
| `templates/aframe.html.j2` | Jinja2 template for the A-Frame scene |
| `configs/scene_config.json` | Default scene spec |
| `configs/demo_kitchen.json` | Demo config (seed 7412, kitchen) |
| `configs/room_types.json` | Reference taxonomy (room types, object tags, gin config names) — not executed |
| `AGENT_GUIDE.md` | LLM workflow documentation, field reference, limitations |

## Critical runtime constraints

- **export_gltf.py must run inside Blender's Python interpreter**, not the system Python. It uses `bpy`, which is only available in Blender.
- **Python 3.11 required** — Infinigen constraint. Use the conda env where Infinigen is installed.
- **Coordinate system conversion**: Blender is Z-up; A-Frame/three.js is Y-up. `export_gltf.py` handles this: position `(X, Y, Z)` → `(X, Z, -Y)`, rotations reordered accordingly.
- **Stage 3 expects manifest.json** at `outputs/{seed}/manifest.json`. If it's missing or malformed, `build_aframe.py` will fail silently or produce an empty scene.

## manifest.json schema

This is the contract between Stage 2 and Stage 3:

```json
{
  "seed": 42,
  "room_type": "Kitchen",
  "object_count": 15,
  "objects": [
    {
      "name": "Chair_0",
      "file": "objects/Chair_0.glb",
      "position": [1.2, 0.0, -0.5],
      "rotation": [0.0, 45.0, 0.0],
      "scale": [1.0, 1.0, 1.0],
      "category": "Seating",
      "polygons": 8432
    }
  ]
}
```

Positions are in A-Frame metres (Y-up). Rotations are Euler XYZ in degrees.

## scene_config.json fields

- `room_type`: one of `Kitchen`, `Bedroom`, `Bathroom`, `DiningRoom`, `LivingRoom`
- `solve_steps_large` / `solve_steps_small`: solver iterations — higher = more objects, much longer runtime
- `object_tags.allow` / `object_tags.deny`: constrain the object vocabulary (see `room_types.json` for tag names)
- `export.texture_resolution`: 256/512/1024/2048 — higher = slower export, better quality
- `export.decimate_ratio`: 0.1 (aggressive) to 1.0 (none) — affects polygon count and file size
- `gin_overrides`: raw Gin config strings passed directly to Infinigen

## Typical runtime

- Stage 1 (Infinigen generation): 8–13 minutes CPU
- Stage 2 (Blender export/bake): 2–5 minutes
- Stage 3 (HTML build): seconds

## Material limitations

`export_gltf.py` bakes only: albedo, roughness, normal, metallic. No transmission, clearcoat, sheen, or emissive baking. Objects with these material properties will lose that detail in the exported .glb.
