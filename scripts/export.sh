#!/usr/bin/env bash
# export.sh — Standalone re-export script
#
# Re-exports an existing scene.blend to per-object glTF with different settings.
#
# Usage:
#   ./scripts/export.sh --blend outputs/42/coarse/scene.blend \
#                        --output outputs/42 \
#                        --texture-resolution 512 \
#                        --decimate-ratio 0.3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_ROOT="$(dirname "$SCRIPT_DIR")"

BLEND_FILE=""
OUTPUT_DIR=""
TEX_RES=1024
DECIMATE=0.5
SEED=0
ROOM_TYPE="Unknown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --blend)              BLEND_FILE="$2"; shift 2 ;;
    --output)             OUTPUT_DIR="$2"; shift 2 ;;
    --texture-resolution) TEX_RES="$2"; shift 2 ;;
    --decimate-ratio)     DECIMATE="$2"; shift 2 ;;
    --seed)               SEED="$2"; shift 2 ;;
    --room-type)          ROOM_TYPE="$2"; shift 2 ;;
    --help)
      echo "Usage: $0 --blend <scene.blend> --output <dir> [options]"
      exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$BLEND_FILE" || -z "$OUTPUT_DIR" ]]; then
  echo "Error: --blend and --output are required"
  exit 1
fi

OBJECTS_DIR="${OUTPUT_DIR}/objects"
mkdir -p "$OBJECTS_DIR"

echo "▸ Exporting per-object glTF..."
echo "  Blend: $BLEND_FILE"
echo "  Output: $OBJECTS_DIR"
echo "  Textures: ${TEX_RES}x${TEX_RES}"
echo "  Decimate: ${DECIMATE}"

# Find blender
BLENDER_BIN=""
if command -v blender &>/dev/null; then
  BLENDER_BIN="blender"
else
  BLENDER_BIN="python -m infinigen.launch_blender"
fi

$BLENDER_BIN \
  --background \
  --python "${SCRIPT_DIR}/export_gltf.py" \
  -- \
  --blend "$BLEND_FILE" \
  --output-dir "$OBJECTS_DIR" \
  --manifest "${OUTPUT_DIR}/manifest.json" \
  --texture-resolution "$TEX_RES" \
  --decimate-ratio "$DECIMATE" \
  --seed "$SEED" \
  --room-type "$ROOM_TYPE"

echo ""
echo "▸ Building A-Frame scene..."

python3 "${SCRIPT_DIR}/build_aframe.py" \
  --manifest "${OUTPUT_DIR}/manifest.json" \
  --template "${HARNESS_ROOT}/templates/aframe.html.j2" \
  --output "${OUTPUT_DIR}/index.html"

echo ""
echo "✓ Done. Serve with:"
echo "  cd ${OUTPUT_DIR} && python -m http.server 8000"
