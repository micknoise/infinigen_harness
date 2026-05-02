#!/usr/bin/env python3
"""
build_aframe.py — Generate an A-Frame HTML scene from a manifest.json

Usage:
    python build_aframe.py \
        --manifest outputs/42/manifest.json \
        --template templates/aframe.html.j2 \
        --output outputs/42/index.html

If --template is not provided or the template file doesn't exist,
uses a built-in default template (no Jinja2 dependency required).
"""

import argparse
import json
import os
import sys


# ── Built-in template (no Jinja2 needed) ──────────────────────────────────────

DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Infinigen Scene — {room_type} (seed {seed})</title>
  <script src="https://aframe.io/releases/1.6.0/aframe.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/aframe-extras@7/dist/aframe-extras.min.js"></script>
  <style>
    body {{ margin: 0; overflow: hidden; }}
  </style>
</head>
<body>
  <a-scene
    renderer="colorManagement: true; physicallyCorrectLights: true"
    background="color: #1a1a2e"
  >
    <!-- Assets: preload all object GLBs -->
    <a-assets timeout="30000">
{asset_tags}
    </a-assets>

    <!-- Scene objects -->
{entity_tags}

    <!-- Lighting -->
    <a-entity light="type: ambient; color: #ffffff; intensity: 0.4"></a-entity>
    <a-entity light="type: directional; color: #ffffff; intensity: 0.8"
              position="2 4 1"></a-entity>

    <!-- Camera with WASD + look controls -->
    <a-entity id="rig" position="0 1.6 3">
      <a-entity camera
                look-controls="pointerLockEnabled: true"
                wasd-controls="acceleration: 20">
      </a-entity>
    </a-entity>
  </a-scene>
</body>
</html>
"""


def build_asset_tag(obj):
    """Build an <a-asset-item> tag for an object."""
    obj_id = obj["name"].replace(" ", "_").replace("/", "_")
    return f'      <a-asset-item id="{obj_id}" src="{obj["file"]}"></a-asset-item>'


def build_entity_tag(obj):
    """Build an <a-entity> tag for an object."""
    obj_id = obj["name"].replace(" ", "_").replace("/", "_")
    pos = obj.get("position", [0, 0, 0])
    rot = obj.get("rotation", [0, 0, 0])
    scl = obj.get("scale", [1, 1, 1])

    pos_str = f"{pos[0]} {pos[1]} {pos[2]}"
    rot_str = f"{rot[0]} {rot[1]} {rot[2]}"
    scl_str = f"{scl[0]} {scl[1]} {scl[2]}"
    category = obj.get("category", "Object")

    return (
        f'    <a-entity\n'
        f'      id="{obj_id}"\n'
        f'      gltf-model="#{obj_id}"\n'
        f'      position="{pos_str}"\n'
        f'      rotation="{rot_str}"\n'
        f'      scale="{scl_str}"\n'
        f'      data-category="{category}"\n'
        f'    ></a-entity>'
    )


def build_with_jinja(manifest, template_path, output_path):
    """Build using Jinja2 template (if available)."""
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        return False

    if not os.path.exists(template_path):
        return False

    template_dir = os.path.dirname(template_path)
    template_name = os.path.basename(template_path)
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_name)
    html = template.render(manifest=manifest)

    with open(output_path, "w") as f:
        f.write(html)
    return True


def build_with_builtin(manifest, output_path):
    """Build using the built-in string template."""
    objects = manifest.get("objects", [])

    asset_tags = "\n".join(build_asset_tag(obj) for obj in objects)
    entity_tags = "\n\n".join(build_entity_tag(obj) for obj in objects)

    html = DEFAULT_TEMPLATE.format(
        room_type=manifest.get("room_type", "Room"),
        seed=manifest.get("seed", 0),
        asset_tags=asset_tags,
        entity_tags=entity_tags,
    )

    with open(output_path, "w") as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description="Build A-Frame HTML from manifest")
    parser.add_argument("--manifest", required=True, help="Path to manifest.json")
    parser.add_argument("--template", default="", help="Path to Jinja2 template")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    with open(args.manifest) as f:
        manifest = json.load(f)

    print(f"  Building A-Frame scene with {manifest.get('object_count', 0)} objects")

    # Try Jinja2 template first, fall back to built-in
    if args.template and build_with_jinja(manifest, args.template, args.output):
        print(f"  ✓ Built with Jinja2 template: {args.template}")
    else:
        build_with_builtin(manifest, args.output)
        print(f"  ✓ Built with default template")

    print(f"  ✓ Output: {args.output}")


if __name__ == "__main__":
    main()
