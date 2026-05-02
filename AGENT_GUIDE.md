# Agent Guide: Infinigen → A-Frame Harness

This document is for Claude Code or any LLM agent driving this harness.

## What you do

1. Translate a user's natural-language room description into `scene_config.json`
2. Run the pipeline
3. Hand back the resulting `index.html` and `objects/` directory

## Step 1: Create scene_config.json

Given a prompt like:

> "a cosy kitchen with a wooden table, four chairs, a fridge, and a window"

Write `configs/scene_config.json`:

```json
{
  "seed": 42,
  "room_type": "Kitchen",
  "single_room": true,
  "terrain_enabled": false,
  "fast_solve": true,
  "solve_steps_large": 50,
  "solve_steps_small": 50,
  "restrict_parent": [],
  "restrict_child_primary": [],
  "restrict_child_secondary": [],
  "extra_gin": [],
  "export": {
    "texture_resolution": 1024,
    "decimate_ratio": 0.5
  }
}
```

### Field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `seed` | int | random | Deterministic randomisation seed |
| `room_type` | string | required | `DiningRoom` `Bathroom` `Bedroom` `Kitchen` `LivingRoom` |
| `single_room` | bool | true | One room vs whole floor plan |
| `terrain_enabled` | bool | false | Outdoor terrain through windows |
| `fast_solve` | bool | true | Fewer solver steps = faster |
| `solve_steps_large` | int | 30 | Iterations for large furniture |
| `solve_steps_small` | int | 30 | Iterations for small items |
| `restrict_parent` | list | [] | Limit room types solved (e.g. `["Kitchen"]`) |
| `restrict_child_primary` | list | [] | Limit primary objects placed |
| `restrict_child_secondary` | list | [] | Limit secondary (on-top-of) objects |
| `extra_gin` | list | [] | Raw Gin config overrides |
| `floor_plan` | string | null | Path to predefined floor plan JSON |
| `export.texture_resolution` | int | 1024 | Baked texture size (256–4096) |
| `export.decimate_ratio` | float | 0.5 | Mesh simplification (0.1 = aggressive, 1.0 = none) |

### Room type mapping

| User says | Config value |
|-----------|-------------|
| kitchen, cooking area, galley | `Kitchen` |
| bedroom, master suite, sleeping area | `Bedroom` |
| bathroom, shower room, WC, ensuite | `Bathroom` |
| living room, lounge, sitting room | `LivingRoom` |
| dining room, eating area | `DiningRoom` |

### About object control

Infinigen places objects via constraint satisfaction — you cannot request
"exactly four chairs". The solver decides what fits given the room geometry and
constraint graph. You can influence results by:

- Adjusting `solve_steps_*` (more steps → denser furnishing)
- Setting `fast_solve: false` (much slower, better arrangements)
- Using `restrict_child_primary` / `restrict_child_secondary` to filter types
- Changing `seed` to get a different arrangement

### Available object tags

Primary (placed directly in the room):
`Bed` `Desk` `Wardrobe` `Shelf` `KitchenCounter` `KitchenIsland`
`Bathtub` `Toilet` `BathroomCounter` `Sofa` `TVStand` `DiningTable`
`Storage` `Seating` `Table` `Lighting`

Secondary (placed on surfaces):
`Sink` `Oven` `Dishwasher` `Microwave` `Monitor` `Lamp` `Book`
`Vase` `PlantContainer` `Utensils` `FoodItem` `Bottle`

## Step 2: Run the pipeline

```bash
./scripts/generate.sh --config configs/scene_config.json
```

This will:
1. Call Infinigen to generate `outputs/{seed}/coarse/scene.blend`
2. Call Blender via `export_gltf.py` to produce per-object `.glb` files
3. Write `outputs/{seed}/manifest.json`
4. Call `build_aframe.py` to produce `outputs/{seed}/index.html`

Generation takes ~8–15 minutes for a single room on CPU.
Export takes ~2–5 minutes depending on texture resolution and object count.

## Step 3: Outputs

```
outputs/{seed}/
├── manifest.json          # Scene graph: list of objects + transforms
├── index.html             # Self-contained A-Frame scene
└── objects/               # One .glb per scene object
    ├── Wall_0.glb
    ├── Floor_0.glb
    ├── KitchenCounter_0.glb
    ├── Chair_0.glb
    ├── Chair_1.glb
    └── ...
```

### manifest.json format

```json
{
  "seed": 42,
  "room_type": "Kitchen",
  "objects": [
    {
      "name": "Chair_0",
      "file": "objects/Chair_0.glb",
      "position": [1.2, 0.0, -0.5],
      "rotation": [0.0, 45.0, 0.0],
      "scale": [1.0, 1.0, 1.0],
      "category": "Seating"
    }
  ]
}
```

Position is in metres, rotation in degrees (Euler XYZ), matching A-Frame
conventions. The export script handles the Blender → A-Frame coordinate
system conversion (Blender Z-up → A-Frame/three.js Y-up).

## Step 4: Serve and view

```bash
cd outputs/{seed}
python -m http.server 8000
# Open http://localhost:8000/index.html
```

## Iteration

To get a variation of the same room:
- Change `seed` and re-run
- Or adjust `solve_steps_*`, toggle `fast_solve`, add/remove restrictions

## Limitations

- Object vocabulary is fixed to Infinigen's procedural generators — you
  cannot request arbitrary objects like "a specific IKEA shelf"
- Materials are baked to albedo/roughness/normal/metallic only — no
  transmission, clearcoat, or sheen
- Geometry can be heavy for mobile WebXR even after decimation
- Solver placement is stochastic, not art-directed
