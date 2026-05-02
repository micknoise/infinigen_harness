# Infinigen → A-Frame Harness

A tool harness that lets Claude Code (or any LLM agent) turn a natural language
prompt into a furnished 3D interior scene — exported as individual glTF files
per object — ready for assembly in A-Frame.

## Architecture

```
 User prompt
 "a small kitchen with a round
  table, two chairs, a gas stove      Claude Code / LLM agent
  and a window"                       ┌──────────────────────────┐
        │                             │ 1. Create scene_config   │
        └────────────────────────────▶│ 2. Run generate.sh       │
                                      │ 3. Run export_gltf.py    │
                                      │ 4. Run build_aframe.py   │
                                      └────────────┬─────────────┘
                                                   │
                          ┌────────────────────────┐│
                          │ Infinigen CLI           ││
                          │ → scene.blend           ││
                          └────────────────────────┘│
                                                   │
                          ┌────────────────────────┐│
                          │ export_gltf.py          ││
                          │ (Blender Python)        ││
                          │ → bake materials        ││
                          │ → decimate meshes       ││
                          │ → per-object .glb       ││
                          │ → manifest.json         ││
                          └────────────────────────┘│
                                                   │
                          ┌────────────────────────┐│
                          │ build_aframe.py         ││
                          │ → index.html            ││
                          └────────────────────────┘│
                                                   ▼
                                      outputs/{seed}/
                                      ├── manifest.json
                                      ├── index.html
                                      └── objects/
                                          ├── floor_001.glb
                                          ├── wall_001.glb
                                          ├── table_001.glb
                                          ├── chair_001.glb
                                          └── ...
```

Each object is a self-contained `.glb` with baked PBR textures. The
`manifest.json` records each object's name, transform, and filename.
`build_aframe.py` reads the manifest and emits an A-Frame HTML scene
that loads every object as a `<a-entity gltf-model="...">`.

## Prerequisites

- Python 3.11 via conda
- Infinigen installed as a Python module
- Blender (installed by Infinigen's setup)
- Linux or macOS (Apple Silicon OK)

### Installing Infinigen

```bash
git clone https://github.com/princeton-vl/infinigen.git
cd infinigen
conda create --name infinigen python=3.11
conda activate infinigen
pip install -e ".[terrain,vis]"
```

## Quick start

```bash
# Generate + export + build A-Frame page, all in one:
./scripts/generate.sh --config configs/scene_config.json
```

## File reference

| File | Purpose |
|------|---------|
| `AGENT_GUIDE.md` | Full instructions for Claude Code |
| `scripts/generate.sh` | Orchestrator: config → Infinigen → export → HTML |
| `scripts/export_gltf.py` | Blender Python: .blend → per-object .glb + manifest |
| `scripts/build_aframe.py` | manifest.json → A-Frame index.html |
| `configs/scene_config.json` | Scene specification |
| `configs/room_types.json` | Reference data for room types and object tags |
| `templates/aframe.html.j2` | Jinja2 template for the A-Frame page |
