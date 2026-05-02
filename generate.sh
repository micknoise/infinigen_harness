#!/usr/bin/env bash
# generate.sh — Orchestrator: config → Infinigen → per-object glTF → A-Frame HTML
#
# Usage:
#   ./scripts/generate.sh --config configs/scene_config.json
#   ./scripts/generate.sh --config configs/scene_config.json --skip-export
#   ./scripts/generate.sh --config configs/scene_config.json --skip-aframe
#   ./scripts/generate.sh --config configs/scene_config.json --export-only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Defaults ──────────────────────────────────────────────────────────────────
CONFIG_FILE=""
SKIP_GENERATE=false
SKIP_EXPORT=false
SKIP_AFRAME=false
OUTPUT_BASE="${HARNESS_ROOT}/outputs"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)       CONFIG_FILE="$2"; shift 2 ;;
    --output)       OUTPUT_BASE="$2"; shift 2 ;;
    --export-only)  SKIP_GENERATE=true; shift ;;
    --skip-export)  SKIP_EXPORT=true; shift ;;
    --skip-aframe)  SKIP_AFRAME=true; shift ;;
    --help)
      echo "Usage: $0 --config <scene_config.json> [--output <dir>] [--export-only] [--skip-export] [--skip-aframe]"
      exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$CONFIG_FILE" ]]; then
  echo "Error: --config is required"
  echo "Usage: $0 --config <scene_config.json>"
  exit 1
fi

# ── Read config with Python (avoids jq dependency) ────────────────────────────
read_config() {
  python3 -c "
import json, sys
cfg = json.load(open('$CONFIG_FILE'))
# Walk dotted path
val = cfg
for key in '$1'.split('.'):
    if isinstance(val, dict):
        val = val.get(key, '$2')
    else:
        val = '$2'
        break
if isinstance(val, bool):
    print(str(val).lower())
elif isinstance(val, list):
    print(json.dumps(val))
else:
    print(val)
"
}

SEED=$(read_config "seed" "$RANDOM")
ROOM_TYPE=$(read_config "room_type" "LivingRoom")
SINGLE_ROOM=$(read_config "single_room" "true")
TERRAIN=$(read_config "terrain_enabled" "false")
FAST_SOLVE=$(read_config "fast_solve" "true")
STEPS_LARGE=$(read_config "solve_steps_large" "30")
STEPS_SMALL=$(read_config "solve_steps_small" "30")
FLOOR_PLAN=$(read_config "floor_plan" "null")
TEX_RES=$(read_config "export.texture_resolution" "1024")
DECIMATE=$(read_config "export.decimate_ratio" "0.5")

RESTRICT_PARENT=$(read_config "restrict_parent" "[]")
RESTRICT_PRIMARY=$(read_config "restrict_child_primary" "[]")
RESTRICT_SECONDARY=$(read_config "restrict_child_secondary" "[]")
EXTRA_GIN=$(read_config "extra_gin" "[]")

OUTPUT_DIR="${OUTPUT_BASE}/${SEED}"
COARSE_DIR="${OUTPUT_DIR}/coarse"
OBJECTS_DIR="${OUTPUT_DIR}/objects"

echo "════════════════════════════════════════════════════════════════"
echo "  Infinigen → A-Frame Harness"
echo "  Seed:      ${SEED}"
echo "  Room:      ${ROOM_TYPE}"
echo "  Output:    ${OUTPUT_DIR}"
echo "════════════════════════════════════════════════════════════════"

# ── Stage 1: Infinigen scene generation ───────────────────────────────────────
if [[ "$SKIP_GENERATE" == "false" ]]; then
  echo ""
  echo "▸ Stage 1: Generating scene with Infinigen..."

  mkdir -p "$COARSE_DIR"

  # Build gin config list
  GIN_CONFIGS=""
  if [[ "$FAST_SOLVE" == "true" ]]; then
    GIN_CONFIGS="fast_solve.gin"
  fi
  if [[ "$SINGLE_ROOM" == "true" ]]; then
    GIN_CONFIGS="${GIN_CONFIGS} singleroom.gin"
  fi

  # Build -p overrides
  GIN_PARAMS="compose_indoors.terrain_enabled=${TERRAIN}"
  GIN_PARAMS="${GIN_PARAMS} restrict_solving.restrict_parent_rooms=[\\\"${ROOM_TYPE}\\\"]"
  GIN_PARAMS="${GIN_PARAMS} compose_indoors.solve_steps_large=${STEPS_LARGE}"
  GIN_PARAMS="${GIN_PARAMS} compose_indoors.solve_steps_small=${STEPS_SMALL}"

  # Optional: restrict object types
  if [[ "$RESTRICT_PRIMARY" != "[]" ]]; then
    # Convert JSON array to Gin format: ["A","B"] → [\"A\",\"B\"]
    GIN_PRIMARY=$(python3 -c "
import json
items = json.loads('${RESTRICT_PRIMARY}')
print('[' + ','.join(['\\\\\"' + i + '\\\\\"' for i in items]) + ']')
")
    GIN_PARAMS="${GIN_PARAMS} restrict_solving.restrict_child_primary=${GIN_PRIMARY}"
  fi

  if [[ "$RESTRICT_SECONDARY" != "[]" ]]; then
    GIN_SECONDARY=$(python3 -c "
import json
items = json.loads('${RESTRICT_SECONDARY}')
print('[' + ','.join(['\\\\\"' + i + '\\\\\"' for i in items]) + ']')
")
    GIN_PARAMS="${GIN_PARAMS} restrict_solving.restrict_child_secondary=${GIN_SECONDARY}"
  fi

  # Optional: predefined floor plan
  if [[ "$FLOOR_PLAN" != "null" ]]; then
    GIN_PARAMS="${GIN_PARAMS} Solver.floor_plan='${FLOOR_PLAN}'"
  fi

  # Append any extra gin overrides
  if [[ "$EXTRA_GIN" != "[]" ]]; then
    EXTRA=$(python3 -c "
import json
items = json.loads('${EXTRA_GIN}')
print(' '.join(items))
")
    GIN_PARAMS="${GIN_PARAMS} ${EXTRA}"
  fi

  echo "  Gin configs: ${GIN_CONFIGS}"
  echo "  Gin params:  ${GIN_PARAMS}"
  echo ""

  # Run Infinigen
  python -m infinigen_examples.generate_indoors \
    --seed "$SEED" \
    --task coarse \
    --output_folder "$COARSE_DIR" \
    -g $GIN_CONFIGS \
    -p $GIN_PARAMS

  echo "  ✓ Scene generated: ${COARSE_DIR}/scene.blend"
fi

# ── Stage 2: Export to per-object glTF ────────────────────────────────────────
if [[ "$SKIP_EXPORT" == "false" ]]; then
  echo ""
  echo "▸ Stage 2: Exporting per-object glTF..."

  mkdir -p "$OBJECTS_DIR"

  # Find blender executable (Infinigen installs it)
  BLENDER_BIN=""
  if command -v blender &>/dev/null; then
    BLENDER_BIN="blender"
  elif [[ -x "$(python3 -c 'import infinigen; import os; print(os.path.dirname(infinigen.__file__))')/../blender/blender" ]]; then
    BLENDER_BIN="$(python3 -c 'import infinigen; import os; print(os.path.dirname(infinigen.__file__))')/../blender/blender"
  else
    # Try the infinigen launcher
    BLENDER_BIN="python -m infinigen.launch_blender"
  fi

  # Run the export script inside Blender's Python
  $BLENDER_BIN \
    --background \
    --python "${SCRIPT_DIR}/export_gltf.py" \
    -- \
    --blend "${COARSE_DIR}/scene.blend" \
    --output-dir "$OBJECTS_DIR" \
    --manifest "${OUTPUT_DIR}/manifest.json" \
    --texture-resolution "$TEX_RES" \
    --decimate-ratio "$DECIMATE" \
    --seed "$SEED" \
    --room-type "$ROOM_TYPE"

  echo "  ✓ Objects exported to: ${OBJECTS_DIR}/"
  echo "  ✓ Manifest: ${OUTPUT_DIR}/manifest.json"
fi

# ── Stage 3: Build A-Frame HTML ───────────────────────────────────────────────
if [[ "$SKIP_AFRAME" == "false" ]]; then
  echo ""
  echo "▸ Stage 3: Building A-Frame scene..."

  python3 "${SCRIPT_DIR}/build_aframe.py" \
    --manifest "${OUTPUT_DIR}/manifest.json" \
    --template "${HARNESS_ROOT}/templates/aframe.html.j2" \
    --output "${OUTPUT_DIR}/index.html"

  echo "  ✓ A-Frame scene: ${OUTPUT_DIR}/index.html"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Done! Serve with:"
echo "    cd ${OUTPUT_DIR} && python -m http.server 8000"
echo "    Open http://localhost:8000/index.html"
echo "════════════════════════════════════════════════════════════════"
