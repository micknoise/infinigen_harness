"""
export_gltf.py — Blender Python script

Run inside Blender:
  blender --background --python export_gltf.py -- \
    --blend scene.blend \
    --output-dir objects/ \
    --manifest manifest.json \
    --texture-resolution 1024 \
    --decimate-ratio 0.5 \
    --seed 42 \
    --room-type Kitchen

Loads an Infinigen-generated .blend, bakes procedural materials to PBR texture
maps, optionally decimates geometry, then exports each mesh object as an
individual .glb file. Writes a manifest.json with the scene graph.
"""

import bpy
import json
import math
import os
import sys
from pathlib import Path
from mathutils import Matrix


# ── Parse args ────────────────────────────────────────────────────────────────

def parse_args():
    """Parse arguments.

    Supports two calling conventions:
      - Direct Python:  python export_gltf.py --blend scene.blend ...
      - Blender mode:   blender --bg --python export_gltf.py -- --blend scene.blend ...
    """
    import argparse

    argv = sys.argv
    # Blender passes script args after "--"; strip Blender's own args first
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]  # strip the script name

    parser = argparse.ArgumentParser(description="Export .blend to per-object glTF")
    parser.add_argument("--blend", default="", help="Path to .blend file")
    parser.add_argument("--output-dir", default="objects", help="Output directory for .glb files")
    parser.add_argument("--manifest", default="manifest.json", help="Output manifest path")
    parser.add_argument("--texture-resolution", type=int, default=1024)
    parser.add_argument("--decimate-ratio", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--room-type", default="Unknown")
    parser.add_argument("--start-index", type=int, default=0, help="Skip objects before this export index")
    parser.add_argument("--skip-manifest", action="store_true", help="Export GLBs only and leave the manifest unchanged")
    a = parser.parse_args(argv)

    return {
        "blend": a.blend,
        "output_dir": a.output_dir,
        "manifest": a.manifest,
        "texture_resolution": a.texture_resolution,
        "decimate_ratio": a.decimate_ratio,
        "seed": a.seed,
        "room_type": a.room_type,
        "start_index": a.start_index,
        "skip_manifest": a.skip_manifest,
    }


# ── Coordinate conversion ────────────────────────────────────────────────────

def blender_to_aframe_position(loc):
    """Convert Blender Z-up to A-Frame/three.js Y-up.
    Blender (X, Y, Z) → A-Frame (X, Z, -Y)
    """
    return [round(loc[0], 4), round(loc[2], 4), round(-loc[1], 4)]


def blender_to_aframe_rotation(rot_euler):
    """Convert Blender Euler rotation to A-Frame degrees.
    This is approximate — for complex rotations, quaternions would be better,
    but A-Frame's position/rotation/scale interface uses Euler degrees.
    """
    # Blender stores radians; A-Frame wants degrees
    # Axis mapping: Blender (X,Y,Z) → A-Frame (X,Z,-Y)
    rx = math.degrees(rot_euler[0])
    ry = math.degrees(rot_euler[2])
    rz = math.degrees(-rot_euler[1])
    return [round(rx, 2), round(ry, 2), round(rz, 2)]


def blender_to_aframe_scale(scale):
    """Scale axes follow the same reorder as position."""
    return [round(scale[0], 4), round(scale[2], 4), round(scale[1], 4)]


# ── Material baking ──────────────────────────────────────────────────────────

def setup_bake_settings(resolution):
    """Configure Blender for material baking."""
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.device = "CPU"  # Safe default; GPU if available
    bpy.context.scene.cycles.samples = 4     # Low samples OK for baking
    bpy.context.scene.cycles.bake_type = "DIFFUSE"


def ensure_uv_map(obj):
    """Ensure the object has a UV map; create one via smart project if not."""
    if obj.type != "MESH":
        return False
    if len(obj.data.uv_layers) == 0:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")
        obj.select_set(False)
    return True


def bake_object_material(obj, output_dir, resolution):
    """Bake procedural materials to texture images for a single object.

    Creates albedo, roughness, normal, and metallic maps.
    Replaces the object's material with a Principled BSDF using the baked maps.

    Returns list of texture file paths created.
    """
    if obj.type != "MESH" or len(obj.data.materials) == 0:
        return []

    if not ensure_uv_map(obj):
        return []

    textures = []
    safe_name = sanitize_name(obj.name)

    # Bake channels: (suffix, bake_type, color_space)
    channels = [
        ("albedo", "DIFFUSE", "sRGB"),
        ("roughness", "ROUGHNESS", "Non-Color"),
        ("normal", "NORMAL", "Non-Color"),
        ("metallic", "GLOSSY", "Non-Color"),
    ]

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    for suffix, bake_type, color_space in channels:
        img_name = f"{safe_name}_{suffix}"
        img_path = os.path.join(output_dir, f"{img_name}.png")

        # Create target image
        img = bpy.data.images.new(img_name, resolution, resolution)
        img.colorspace_settings.name = color_space

        # Create an image texture node in each material slot and set it active
        for mat_slot in obj.material_slots:
            mat = mat_slot.material
            if mat is None or not mat.use_nodes:
                continue
            nodes = mat.node_tree.nodes
            # Create temp image node for bake target
            bake_node = nodes.new("ShaderNodeTexImage")
            bake_node.image = img
            bake_node.name = "__bake_target__"
            nodes.active = bake_node

        try:
            bpy.context.scene.cycles.bake_type = bake_type
            if bake_type == "DIFFUSE":
                bpy.context.scene.render.bake.use_pass_direct = False
                bpy.context.scene.render.bake.use_pass_indirect = False
                bpy.context.scene.render.bake.use_pass_color = True
            bpy.ops.object.bake(type=bake_type)
            img.filepath_raw = img_path
            img.file_format = "PNG"
            img.save()
            textures.append(img_path)
        except Exception as e:
            print(f"  Warning: failed to bake {suffix} for {obj.name}: {e}")

        # Clean up temp bake nodes
        for mat_slot in obj.material_slots:
            mat = mat_slot.material
            if mat is None or not mat.use_nodes:
                continue
            nodes = mat.node_tree.nodes
            bake_nodes = [n for n in nodes if n.name == "__bake_target__"]
            for n in bake_nodes:
                nodes.remove(n)

    obj.select_set(False)
    return textures


# ── Decimation ────────────────────────────────────────────────────────────────

def decimate_object(obj, ratio):
    """Apply a decimate modifier to reduce polygon count."""
    if obj.type != "MESH" or ratio >= 1.0:
        return

    # Skip very small meshes
    if len(obj.data.polygons) < 100:
        return

    mod = obj.modifiers.new(name="Decimate_Export", type="DECIMATE")
    mod.ratio = ratio
    mod.use_collapse_triangulate = True

    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception as e:
        print(f"  Warning: decimation failed for {obj.name}: {e}")
        # Remove the modifier if apply failed
        if mod.name in obj.modifiers:
            obj.modifiers.remove(mod)


# ── Export ────────────────────────────────────────────────────────────────────

def sanitize_name(name):
    """Create a filesystem-safe name from a Blender object name."""
    safe = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    safe = "".join(c for c in safe if c.isalnum() or c in "_-.")
    return safe


def make_export_copy(obj, export_collection):
    """Duplicate an object for export with its transform reset to identity.

    The manifest carries each object's world-space transform for A-Frame, so the
    exported GLB must remain in object-local space to avoid double-applying
    placement in the browser.
    """
    export_obj = obj.copy()
    export_obj.data = obj.data.copy()
    export_obj.animation_data_clear()
    export_obj.parent = None
    export_collection.objects.link(export_obj)

    export_obj.matrix_world = Matrix.Identity(4)
    export_obj.location = (0.0, 0.0, 0.0)
    export_obj.rotation_euler = (0.0, 0.0, 0.0)
    export_obj.scale = (1.0, 1.0, 1.0)
    export_obj.data.update()

    return export_obj


def cleanup_export_copy(export_obj, export_collection):
    """Remove the temporary export object and its copied mesh data."""
    mesh_data = export_obj.data
    export_collection.objects.unlink(export_obj)
    bpy.data.objects.remove(export_obj)
    bpy.data.meshes.remove(mesh_data)


def export_object_glb(obj, output_path, export_collection):
    """Export a single object as a .glb file with local-space geometry."""
    export_obj = make_export_copy(obj, export_collection)

    # Deselect all, select only the temporary export copy
    bpy.ops.object.select_all(action="DESELECT")
    export_obj.select_set(True)
    bpy.context.view_layer.objects.active = export_obj

    try:
        bpy.ops.export_scene.gltf(
            filepath=output_path,
            use_selection=True,
            export_format="GLB",
            export_apply=True,
            export_yup=True,           # Convert to Y-up for three.js
            export_texcoords=True,
            export_normals=True,
            export_materials="EXPORT",
            export_image_format="AUTO",
        )
    except Exception as e:
        print(f"  Warning: glTF export failed for {obj.name}: {e}")
        cleanup_export_copy(export_obj, export_collection)
        return False

    bpy.ops.object.select_all(action="DESELECT")
    cleanup_export_copy(export_obj, export_collection)
    return True


def categorize_object(obj):
    """Try to determine an object category from its name or custom properties."""
    name = obj.name.lower()

    # Common Infinigen naming patterns
    categories = {
        "wall": "Architecture",
        "floor": "Architecture",
        "ceiling": "Architecture",
        "door": "Architecture",
        "window": "Architecture",
        "stair": "Architecture",
        "bed": "Furniture",
        "sofa": "Furniture",
        "couch": "Furniture",
        "chair": "Seating",
        "stool": "Seating",
        "table": "Furniture",
        "desk": "Furniture",
        "counter": "Furniture",
        "cabinet": "Storage",
        "shelf": "Storage",
        "wardrobe": "Storage",
        "drawer": "Storage",
        "sink": "Fixture",
        "toilet": "Fixture",
        "bathtub": "Fixture",
        "shower": "Fixture",
        "oven": "Appliance",
        "fridge": "Appliance",
        "microwave": "Appliance",
        "dishwasher": "Appliance",
        "toaster": "Appliance",
        "lamp": "Lighting",
        "light": "Lighting",
        "monitor": "Electronics",
        "tv": "Electronics",
        "book": "Decor",
        "vase": "Decor",
        "plant": "Decor",
        "bottle": "Decor",
        "utensil": "Decor",
        "cup": "Decor",
        "plate": "Decor",
    }

    for keyword, category in categories.items():
        if keyword in name:
            return category

    return "Object"


def should_export_object(obj):
    """Return whether a Blender mesh object should be part of the scene export."""
    collection_names = {collection.name for collection in obj.users_collection}

    # Infinigen keeps portal cutters, room shell placeholders, and reusable door
    # assembly source meshes in dedicated collections. They are helper geometry,
    # not visible scene instances, and exporting them produces duplicate or
    # blocking meshes in A-Frame.
    for name in collection_names:
        if name.startswith("placeholders:"):
            return False
        if "base_elements" in name:
            return False

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    blend_file = args["blend"]
    output_dir = args["output_dir"]
    manifest_path = args["manifest"]
    tex_res = args["texture_resolution"]
    decimate_ratio = args["decimate_ratio"]
    start_index = max(args["start_index"], 0)

    print(f"\n{'='*60}")
    print(f"  export_gltf.py")
    print(f"  Input:      {blend_file}")
    print(f"  Output:     {output_dir}")
    print(f"  Textures:   {tex_res}x{tex_res}")
    print(f"  Decimate:   {decimate_ratio}")
    print(f"{'='*60}\n")

    # Load the .blend file
    if blend_file and os.path.exists(blend_file):
        bpy.ops.wm.open_mainfile(filepath=blend_file)
    elif blend_file:
        print(f"Error: blend file not found: {blend_file}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Setup baking
    setup_bake_settings(tex_res)

    # Collect exportable objects (mesh objects at the top level or one deep)
    exportable = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if not should_export_object(obj):
            continue
        # Skip objects that are too small to matter
        dims = obj.dimensions
        if max(dims) < 0.001:
            continue
        exportable.append(obj)

    print(f"  Found {len(exportable)} mesh objects to export\n")

    manifest_objects = []
    export_collection = bpy.data.collections.new("__aframe_export__")
    bpy.context.scene.collection.children.link(export_collection)

    for i, obj in enumerate(exportable):
        if i < start_index:
            continue

        safe_name = sanitize_name(obj.name)
        glb_path = os.path.join(output_dir, f"{safe_name}.glb")

        print(f"  [{i+1}/{len(exportable)}] {obj.name}")
        print(f"    Polygons: {len(obj.data.polygons)}")

        # Bake materials
        print(f"    Baking materials ({tex_res}x{tex_res})...")
        try:
            bake_object_material(obj, output_dir, tex_res)
        except Exception as e:
            print(f"    Warning: material bake failed, exporting with defaults: {e}")

        # Decimate
        if decimate_ratio < 1.0:
            orig_polys = len(obj.data.polygons)
            decimate_object(obj, decimate_ratio)
            new_polys = len(obj.data.polygons)
            print(f"    Decimated: {orig_polys} → {new_polys} polys")

        # Export glb
        print(f"    Exporting: {safe_name}.glb")
        success = export_object_glb(obj, glb_path, export_collection)

        if success:
            # Record the original world transform for A-Frame placement. The
            # temporary export copy is reset to identity before writing the GLB.
            loc = obj.matrix_world.to_translation()
            rot = obj.matrix_world.to_euler("XYZ")
            scl = obj.matrix_world.to_scale()

            manifest_objects.append({
                "name": obj.name,
                "file": f"objects/{safe_name}.glb",
                "position": blender_to_aframe_position(loc),
                "rotation": blender_to_aframe_rotation(rot),
                "scale": blender_to_aframe_scale(scl),
                "category": categorize_object(obj),
                "polygons": len(obj.data.polygons),
            })

        print()

    if not args["skip_manifest"]:
        manifest = {
            "seed": args["seed"],
            "room_type": args["room_type"],
            "object_count": len(manifest_objects),
            "objects": manifest_objects,
        }

        os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    bpy.context.scene.collection.children.unlink(export_collection)
    bpy.data.collections.remove(export_collection)

    print(f"\n  ✓ Exported {len(exportable) - start_index} objects")
    if args["skip_manifest"]:
        print(f"  ✓ Manifest left unchanged: {manifest_path}")
    else:
        print(f"  ✓ Manifest written to {manifest_path}")


if __name__ == "__main__":
    main()
