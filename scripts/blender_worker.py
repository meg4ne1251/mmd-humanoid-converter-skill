"""Blender-side implementation. Invoke through mmd_cli.py, not system Python."""
import hashlib
from array import array
import json
import math
from pathlib import Path
import re
import sys
import traceback
import uuid

import bpy
from mathutils import Vector, Matrix


HUMANOID = {"Parent", "Hips", "Spine1", "Head"} | {
    f"{bone}_{side}" for side in ("L", "R")
    for bone in ("UpArm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot")
}
NON_BONE_GROUPS = {"mmd_edge_scale", "mmd_vertex_order"}
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
OPS = {
    "delete_objects": {"names"},
    "clear_constraints": set(),
    "reset_pose": set(),
    "transfer_weights": {"pairs"},
    "edit_bones": {"add", "update", "delete"},
    "rename_bones": {"mapping"},
    "connect_bones": {"tolerance"},
    "principled_materials": {"materials"},
    "separate_materials": {"object", "parts"},
    "rename_shape_keys": {"mapping", "objects"},
    "clear_shape_keys": {"objects"},
    "rename_materials": {"mapping", "ascii_only", "tidy_toon"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finished(result):
    require(result == {"FINISHED"}, f"Operator did not finish: {result}")


def keys(value, allowed, required=()):
    require(isinstance(value, dict), "Expected a JSON object")
    require(not set(value) - set(allowed), f"Unknown fields: {sorted(set(value) - set(allowed))}")
    require(set(required) <= set(value), f"Missing fields: {sorted(set(required) - set(value))}")


def finite_vector(value):
    require(isinstance(value, (list, tuple)) and len(value) == 3
            and all(isinstance(n, (int, float)) and math.isfinite(n) for n in value),
            f"Expected three finite coordinates: {value}")
    return Vector(value)


def activate(obj):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        finished(bpy.ops.object.mode_set(mode="OBJECT"))
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.hide_viewport = False
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    require(obj.name in bpy.context.view_layer.objects, f"Object excluded from view layer: {obj.name}")


def weights(mesh, name):
    group = mesh.vertex_groups.get(name)
    if group is None:
        return {}
    return {v.index: g.weight for v in mesh.data.vertices for g in v.groups if g.group == group.index}


def weight_stats(mesh):
    result = {g.index: {"name": g.name, "vertices": 0, "sum": 0.0} for g in mesh.vertex_groups}
    for vertex in mesh.data.vertices:
        for group in vertex.groups:
            if group.weight > 0:
                result[group.group]["vertices"] += 1
                result[group.group]["sum"] += group.weight
    return list(result.values())


def mesh_signature(mesh):
    """Geometry/shape keys must not be baked or changed by a weight operation."""
    digest = hashlib.sha256()

    def coordinates(collection):
        values = array("f", [0.0]) * (len(collection) * 3)
        collection.foreach_get("co", values)
        digest.update(values.tobytes())

    coordinates(mesh.data.vertices)
    for collection, field in [(mesh.data.loops, "vertex_index"), (mesh.data.polygons, "loop_total")]:
        values = array("i", [0]) * len(collection)
        collection.foreach_get(field, values)
        digest.update(values.tobytes())
    if mesh.data.shape_keys:
        for key in mesh.data.shape_keys.key_blocks:
            digest.update(key.name.encode() + b"\0")
            coordinates(key.data)
    return digest.hexdigest()


def scene_info():
    objects, arms, materials = [], [], {}
    for obj in bpy.context.scene.objects:
        item = {"name": obj.name, "type": obj.type, "parent": obj.parent.name if obj.parent else None,
                "hidden": obj.hide_get(), "matrix_world": [list(row) for row in obj.matrix_world]}
        if obj.type == "MESH":
            item.update(vertices=len(obj.data.vertices), polygons=len(obj.data.polygons),
                        mesh_users=obj.data.users, vertex_groups=weight_stats(obj),
                        armatures=[m.object.name if m.object else None for m in obj.modifiers if m.type == "ARMATURE"],
                        materials=[s.material.name if s.material else None for s in obj.material_slots],
                        uv_layers=[u.name for u in obj.data.uv_layers],
                        shape_keys=[k.name for k in obj.data.shape_keys.key_blocks] if obj.data.shape_keys else [])
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.name not in materials:
                    materials[mat.name] = {
                        "name": mat.name,
                        "nodes": [{"name": n.name, "type": n.type,
                                   **({"image": n.image.name if n.image else None,
                                       "filepath": n.image.filepath if n.image else None,
                                       "image_users": n.image.users if n.image else 0}
                                      if n.type == "TEX_IMAGE" else {})}
                                  for n in mat.node_tree.nodes] if mat.node_tree else [],
                    }
        objects.append(item)
        if obj.type == "ARMATURE":
            arms.append({"name": obj.name, "bones": [
                {"name": b.name, "parent": b.parent.name if b.parent else None,
                 "head": list(b.head_local), "tail": list(b.tail_local), "roll_matrix": [list(r) for r in b.matrix_local],
                 "use_connect": b.use_connect, "use_deform": b.use_deform,
                 "pose_matrix_basis": [list(r) for r in obj.pose.bones[b.name].matrix_basis],
                 "constraints": [c.type for c in obj.pose.bones[b.name].constraints]}
                for b in obj.data.bones],
                "collections": [{"name": c.name, "visible": c.is_visible} for c in obj.data.collections_all]})
    return {"objects": objects, "armatures": arms, "materials": list(materials.values())}


def load_input(job):
    source = Path(job["input"])
    suffix = source.suffix.lower()
    if suffix == ".blend":
        finished(bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False))
    else:
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        if suffix == ".fbx":
            import addon_utils
            addon_utils.enable("io_scene_fbx", default_set=False)
            finished(bpy.ops.import_scene.fbx(filepath=str(source), use_anim=False))
        else:
            import addon_utils
            candidates = [m.__name__ for m in addon_utils.modules()
                          if m.__name__ == "mmd_tools" or m.__name__.endswith(".mmd_tools")]
            module = job.get("mmd_addon")
            if not module:
                require(len(candidates) == 1, f"Expected one MMD Tools addon; found {candidates}. Use --mmd-addon.")
                module = candidates[0]
            addon_utils.enable(module, default_set=False)
            options = dict(job.get("import_options") or {})
            require(not set(options) & {"filepath", "directory", "files", "save_log"},
                    "Import options cannot override input path or enable logs beside the source")
            REPORT["import_options"] = json.loads(json.dumps(options))
            # JSON arrays represent Blender enum-flag sets.
            rna = bpy.ops.mmd_tools.import_model.get_rna_type()
            for name, value in list(options.items()):
                prop = rna.properties.get(name)
                require(prop is not None, f"Unknown MMD import option: {name}")
                if prop.type == "ENUM" and prop.is_enum_flag:
                    require(isinstance(value, list), f"Import enum flag must be an array: {name}")
                    options[name] = set(value)
            finished(bpy.ops.mmd_tools.import_model("EXEC_DEFAULT", filepath=str(source), save_log=False, **options))
            require(any(o.type == "ARMATURE" for o in bpy.context.scene.objects)
                    and any(o.type == "MESH" for o in bpy.context.scene.objects),
                    "MMD import produced no rig or mesh; inspect blender.log")
    bpy.context.view_layer.update()


class Rig:
    def __init__(self, armature=None, meshes=None, material_only=False):
        if material_only:
            require(isinstance(meshes, list) and meshes and len(meshes) == len(set(meshes)),
                    "Material-only plans must list model meshes")
            require(all(n in bpy.context.scene.objects and bpy.context.scene.objects[n].type == "MESH" for n in meshes),
                    "Material-only mesh does not exist")
            self.arm = None
            self.meshes = [bpy.data.objects[n] for n in meshes]
            return
        arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
        require(len(arms) == 1, f"Expected one armature; found {[o.name for o in arms]}")
        self.arm = arms[0]
        require(not armature or self.arm.name == armature, f"Armature not found: {armature}")
        bound = [o for o in bpy.context.scene.objects if o.type == "MESH"
                 and any(m.type == "ARMATURE" and m.object == self.arm for m in o.modifiers)]
        require(bound, "No meshes bound to the armature")
        require(meshes is None or (len(meshes) == len(set(meshes)) and set(meshes) == {o.name for o in bound}),
                f"meshes must list all meshes bound to {self.arm.name}: {[o.name for o in bound]}")
        self.meshes = bound

    def used_materials(self):
        return {s.material.name: s.material for o in self.meshes for s in o.material_slots if s.material}

    def has_weight(self, name):
        return any(any(w > 0 for w in weights(o, name).values()) for o in self.meshes)

    def verify(self, required_bones=()):
        errors, warnings, meshes = [], [], []
        bones = {b.name for b in self.arm.data.bones} if self.arm else set()
        missing = set(required_bones) - bones
        if missing:
            errors.append(f"Missing required bones: {sorted(missing)}")
        for bone in self.arm.data.bones if self.arm else []:
            if bone.length <= 1e-8 or not all(math.isfinite(v) for row in bone.matrix_local for v in row):
                errors.append(f"Invalid bone geometry: {bone.name}")
        for mesh in self.meshes:
            names = {g.index: g.name for g in mesh.vertex_groups}
            orphans, unweighted, nonfinite = set(), 0, 0
            for vertex in mesh.data.vertices:
                influence = 0.0
                if not all(math.isfinite(v) for v in vertex.co):
                    nonfinite += 1
                for group in vertex.groups:
                    if not math.isfinite(group.weight) or not 0 <= group.weight <= 1:
                        errors.append(f"Invalid weight on {mesh.name}, vertex {vertex.index}")
                    if group.weight > 0:
                        name = names[group.group]
                        if name in bones:
                            influence += group.weight
                        elif self.arm and name not in NON_BONE_GROUPS:
                            orphans.add(name)
                if self.arm and influence == 0:
                    unweighted += 1
            if nonfinite:
                errors.append(f"{mesh.name}: {nonfinite} non-finite vertices")
            if orphans:
                errors.append(f"{mesh.name}: weighted groups without bones: {sorted(orphans)}")
            if unweighted:
                warnings.append(f"{mesh.name}: {unweighted} vertices without bone weights")
            if not mesh.data.uv_layers:
                warnings.append(f"{mesh.name}: no UV layer")
            meshes.append({"name": mesh.name, "vertices": len(mesh.data.vertices),
                           "polygons": len(mesh.data.polygons), "unweighted_vertices": unweighted,
                           "uv_layers": [u.name for u in mesh.data.uv_layers],
                           "shape_keys": [k.name for k in mesh.data.shape_keys.key_blocks] if mesh.data.shape_keys else [],
                           "materials": [s.material.name if s.material else None for s in mesh.material_slots],
                           "used_materials": sorted({mesh.material_slots[p.material_index].material.name
                                                    for p in mesh.data.polygons
                                                    if p.material_index < len(mesh.material_slots)
                                                    and mesh.material_slots[p.material_index].material})})
        for mat in self.used_materials().values():
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image:
                        image = node.image
                        if image.source == "FILE" and not image.packed_file and not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
                            errors.append(f"Missing image: {mat.name}/{node.name}: {image.filepath}")
        return {"ok": not errors, "errors": errors, "warnings": warnings, "meshes": meshes,
                "bone_count": len(bones), "required_bones": sorted(required_bones)}

    def delete_objects(self, op):
        names = op["names"]
        require(len(names) == len(set(names)), "Duplicate object deletion")
        require(not set(names) & {self.arm.name, *(o.name for o in self.meshes)}, "Cannot delete the rig or its model meshes")
        require(all(n in bpy.context.scene.objects for n in names), "Deletion object does not exist in scene")
        for obj in bpy.context.scene.objects:
            if obj.name not in names and obj.parent and obj.parent.name in names:
                matrix = obj.matrix_world.copy()
                obj.parent = None
                obj.matrix_world = matrix
        for name in names:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        return {"deleted": names}

    def clear_constraints(self, op):
        count = 0
        for bone in self.arm.pose.bones:
            for constraint in list(bone.constraints):
                bone.constraints.remove(constraint)
                count += 1
        return {"removed": count}

    def reset_pose(self, op):
        require(not self.arm.animation_data or not self.arm.animation_data.action,
                "Resetting an animated pose is not supported")
        for bone in self.arm.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        return {"reset": len(self.arm.pose.bones)}

    def transfer_weights(self, op):
        pairs = op["pairs"]
        seen, results = set(), []
        signatures = {o.name: mesh_signature(o) for o in self.meshes}
        for pair in pairs:
            keys(pair, {"source", "target", "mode"}, {"source", "target"})
            src, dst, mode = pair["source"], pair["target"], pair.get("mode", "ADD")
            require(src != dst and src not in seen, "Duplicate or self weight transfer")
            seen.add(src)
            require(src in self.arm.data.bones and dst in self.arm.data.bones, f"Missing source/target bone: {src} → {dst}")
            require(mode in {"ADD", "SET"}, f"Unknown transfer mode: {mode}")
            found = False
            for mesh in self.meshes:
                if src not in mesh.vertex_groups:
                    continue
                found = True
                before, target = weights(mesh, src), weights(mesh, dst)
                expected = dict(target)
                for vertex, value in before.items():
                    result = value + target.get(vertex, 0) if mode == "ADD" else value
                    require(result <= 1.0 + 1e-6, f"Weight overflow on {mesh.name}/{src}, vertex {vertex}: {result}")
                    expected[vertex] = min(1.0, result)
                if mesh.data.users > 1:
                    mesh.data = mesh.data.copy()
                if dst not in mesh.vertex_groups:
                    mesh.vertex_groups.new(name=dst)
                activate(mesh)
                modifier = mesh.modifiers.new("MMD_CLI_Weight", "VERTEX_WEIGHT_MIX")
                modifier.mix_mode, modifier.mix_set, modifier.mask_constant = mode, "B", 1.0
                modifier.vertex_group_a, modifier.vertex_group_b = dst, src
                finished(bpy.ops.object.modifier_apply(modifier=modifier.name))
                actual = weights(mesh, dst)
                require(all(abs(actual.get(i, 0) - expected.get(i, 0)) < 1e-5
                            for i in set(actual) | set(expected)), f"Weight verification failed: {mesh.name}/{src}")
                mesh.vertex_groups.remove(mesh.vertex_groups[src])
                results.append({"mesh": mesh.name, **pair, "vertices": len(before)})
            require(found, f"Source vertex group not found on any model mesh: {src}")
        require(all(mesh_signature(o) == signatures[o.name] for o in self.meshes),
                "Weight modifier changed mesh geometry or shape keys")
        return {"transfers": results}

    def edit_bones(self, op):
        additions, updates, deletions = op.get("add", []), op.get("update", {}), op.get("delete", [])
        old = {b.name: b for b in self.arm.data.bones}
        added = [b["name"] for b in additions]
        require(len(added) == len(set(added)) and not set(added) & set(old), "Added bone names must be new and unique")
        require(set(updates) <= set(old) | set(added), "Updated bone does not exist")
        require(set(deletions) <= set(old) and len(deletions) == len(set(deletions)), "Invalid bone deletion")
        for name in deletions:
            require(not self.has_weight(name), f"Bone still carries weight; transfer first: {name}")
        for bone in additions:
            keys(bone, {"name", "head", "tail", "parent", "use_deform"}, {"name", "head", "tail"})
        for name, changes in updates.items():
            keys(changes, {"head", "tail", "roll", "parent", "use_deform", "allow_weighted_head_move"})
            if "head" in changes and name in old:
                moved = (finite_vector(changes["head"]) - old[name].head_local).length > 1e-7
                require(not moved or not self.has_weight(name) or changes.get("allow_weighted_head_move") is True,
                        f"Refusing to move weighted bone head without explicit override: {name}")
        parents = {n: b.parent.name if b.parent else None for n, b in old.items()}
        parents.update({b["name"]: b.get("parent") for b in additions})
        parents.update({n: v["parent"] for n, v in updates.items() if "parent" in v})
        for name, parent in parents.items():
            if name in deletions:
                continue
            require(parent is None or (parent in parents and parent not in deletions), f"Explicitly reparent surviving child: {name} → {parent}")
            chain, node = {name}, parent
            while node:
                require(node not in chain, f"Parent cycle involving {name}")
                chain.add(node)
                node = parents.get(node)
        connected = {b.name for b in old.values() if b.use_connect}
        heads = {b.name: b.head_local.copy() for b in old.values()}
        activate(self.arm)
        finished(bpy.ops.object.mode_set(mode="EDIT"))
        eb = self.arm.data.edit_bones
        for bone in eb:
            bone.use_connect = False
        for spec in additions:
            bone = eb.new(spec["name"])
            bone.head, bone.tail = finite_vector(spec["head"]), finite_vector(spec["tail"])
            bone.use_deform = spec.get("use_deform", False)
        for name, changes in updates.items():
            bone = eb[name]
            for field in ("head", "tail"):
                if field in changes:
                    setattr(bone, field, finite_vector(changes[field]))
            if "roll" in changes:
                require(math.isfinite(changes["roll"]), "Bone roll must be finite radians")
                bone.roll = changes["roll"]
            if "use_deform" in changes:
                bone.use_deform = bool(changes["use_deform"])
        for name, parent in parents.items():
            if name not in deletions:
                eb[name].parent = eb[parent] if parent else None
        for name in deletions:
            eb.remove(eb[name])
        for name in connected - set(deletions):
            bone = eb[name]
            if bone.parent and (bone.head - bone.parent.tail).length <= 1e-7:
                bone.use_connect = True
        for bone in eb:
            require(bone.length > 1e-8, f"Zero-length bone: {bone.name}")
            if bone.name in heads and "head" not in updates.get(bone.name, {}):
                require((bone.head - heads[bone.name]).length <= 1e-7, f"Unexpected head movement: {bone.name}")
        finished(bpy.ops.object.mode_set(mode="OBJECT"))
        for mesh in self.meshes:
            for name in deletions:
                group = mesh.vertex_groups.get(name)
                if group:
                    mesh.vertex_groups.remove(group)
        return {"added": added, "updated": list(updates), "deleted": deletions}

    def rename_bones(self, op):
        mapping = op["mapping"]
        bones = self.arm.data.bones
        validate_rename(mapping, set(bones.keys()))
        for mesh in self.meshes:
            require(not (set(mapping.values()) - set(mapping)) & set(mesh.vertex_groups.keys()),
                    f"Vertex group name collision on {mesh.name}")
        temp = {}
        for src, dst in mapping.items():
            token = "MMDCLI_" + uuid.uuid4().hex
            bones[src].name = token
            temp[token] = dst
        for token, dst in temp.items():
            bones[token].name = dst
        require(set(mapping.values()) <= set(bones.keys()), "Bone rename was truncated or changed")
        for mesh in self.meshes:
            require(not (set(mapping) - set(mapping.values())) & set(mesh.vertex_groups.keys()),
                    f"Vertex group did not follow rename: {mesh.name}")
        return {"renamed": mapping}

    def connect_bones(self, op):
        tolerance = op.get("tolerance", 1e-7)
        require(0 <= tolerance <= 1e-5, "Connection tolerance must be between 0 and 1e-5 Blender units")
        activate(self.arm)
        finished(bpy.ops.object.mode_set(mode="EDIT"))
        connected, shift = [], 0.0
        for bone in self.arm.data.edit_bones:
            if bone.parent and (bone.head - bone.parent.tail).length <= tolerance:
                before = bone.head.copy()
                bone.use_connect = True
                shift = max(shift, (bone.head - before).length)
                connected.append(bone.name)
        finished(bpy.ops.object.mode_set(mode="OBJECT"))
        self.arm.data.display_type, self.arm.show_in_front = "OCTAHEDRAL", True
        return {"connected": connected, "max_head_shift": shift}

    def principled_materials(self, op):
        materials = self.used_materials()
        result = []
        for name, spec in op["materials"].items():
            keys(spec, {"base_color_node", "alpha"}, {"base_color_node"})
            require(name in materials, f"Material not used by model: {name}")
            mat = materials[name]
            mat.use_nodes = True
            tree = mat.node_tree
            outputs = [n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
            require(len(outputs) <= 1, f"Ambiguous output: {name}")
            output = outputs[0] if outputs else tree.nodes.new("ShaderNodeOutputMaterial")
            shaders = [n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"]
            require(len(shaders) <= 1, f"Ambiguous Principled shader: {name}")
            shader = shaders[0] if shaders else tree.nodes.new("ShaderNodeBsdfPrincipled")
            base = spec["base_color_node"]
            if base is not None:
                node = tree.nodes.get(base)
                require(node and node.type == "TEX_IMAGE" and node.image, f"Invalid base-color image node: {name}/{base}")
                tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])
                if spec.get("alpha", True) and node.image.channels == 4:
                    tree.links.new(node.outputs["Alpha"], shader.inputs["Alpha"])
            tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
            shader.inputs["Roughness"].default_value = 0.8
            specular = shader.inputs.get("Specular IOR Level") or shader.inputs.get("Specular")
            if specular is not None:
                specular.default_value = 0
            result.append(name)
        return {"rewired": result}

    def separate_materials(self, op):
        mesh = next((o for o in self.meshes if o.name == op["object"]), None)
        require(mesh is not None, f"Model mesh not found: {op['object']}")
        parts = op["parts"]
        require(parts and all(names for names in parts.values()), "Part mappings must not be empty")
        target_by_mat = {}
        for part, names in parts.items():
            require(part == mesh.name or part not in bpy.data.objects, f"Part object name collision: {part}")
            for name in names:
                require(name not in target_by_mat, f"Material assigned to multiple parts: {name}")
                target_by_mat[name] = part
        used = {mesh.material_slots[p.material_index].material.name
                if p.material_index < len(mesh.material_slots) and mesh.material_slots[p.material_index].material else None
                for p in mesh.data.polygons}
        require(None not in used and used == set(target_by_mat), f"Part mapping must cover exactly the used materials: {sorted(str(n) for n in used)}")
        shape_names = set(mesh.data.shape_keys.key_blocks.keys()) if mesh.data.shape_keys else set()
        if mesh.data.users > 1:
            mesh.data = mesh.data.copy()
        before = set(bpy.data.objects)
        activate(mesh)
        finished(bpy.ops.object.mode_set(mode="EDIT"))
        finished(bpy.ops.mesh.select_all(action="SELECT"))
        finished(bpy.ops.mesh.separate(type="MATERIAL"))
        finished(bpy.ops.object.mode_set(mode="OBJECT"))
        fragments = [o for o in bpy.data.objects if o == mesh or o not in before]
        buckets = {name: [] for name in parts}
        for obj in fragments:
            actual = {obj.material_slots[p.material_index].material.name for p in obj.data.polygons}
            targets = {target_by_mat[name] for name in actual}
            require(len(targets) == 1, f"Ambiguous separated fragment: {obj.name}")
            buckets[targets.pop()].append(obj)
        self.meshes.remove(mesh)
        for name, objects in buckets.items():
            require(objects, f"No geometry for part: {name}")
            activate(objects[0])
            for obj in objects:
                obj.select_set(True)
            if len(objects) > 1:
                finished(bpy.ops.object.join())
            obj = bpy.context.object
            obj.name = name
            require(obj.name == name, f"Part name collision: {name}")
            obj.data.name = name
            actual_shapes = set(obj.data.shape_keys.key_blocks.keys()) if obj.data.shape_keys else set()
            require(actual_shapes == shape_names, f"Shape keys changed during separation/join: {name}")
            self.meshes.append(obj)
        return {"parts": [o.name for o in self.meshes]}

    def selected_meshes(self, names=None):
        by_name = {o.name: o for o in self.meshes}
        require(names is None or set(names) <= set(by_name), "Object is not a model mesh")
        return self.meshes if names is None else [by_name[n] for n in names]

    def rename_shape_keys(self, op):
        mapping = op.get("mapping", {"あ": "a", "い": "i", "う": "u", "え": "e", "お": "o"})
        results = []
        for mesh in self.selected_meshes(op.get("objects")):
            if not mesh.data.shape_keys:
                continue
            block = mesh.data.shape_keys.key_blocks
            local = {src: dst for src, dst in mapping.items() if src in block}
            validate_rename(local, set(block.keys()))
            renamed = []
            for src, dst in local.items():
                key = block[src]
                key.name = "MMDCLI_" + uuid.uuid4().hex
                renamed.append((key, dst))
            for key, dst in renamed:
                key.name = dst
            results.append({"mesh": mesh.name, "renamed": local})
        return {"meshes": results}

    def clear_shape_keys(self, op):
        meshes = self.selected_meshes(op["objects"])
        for mesh in meshes:
            mesh.shape_key_clear()
        return {"cleared": [o.name for o in meshes]}

    def rename_materials(self, op):
        mapping = op["mapping"]
        materials = self.used_materials()
        names = {src: spec["name"] for src, spec in mapping.items()}
        validate_rename(names, set(bpy.data.materials.keys()))
        require(set(mapping) <= set(materials), "Renamed material must be used by model")
        require(not op.get("ascii_only", True) or all(NAME.fullmatch(n) for n in names.values()),
                "Material names must be ASCII letters/digits/underscore/hyphen")
        require(len({n.casefold() for n in names.values()}) == len(names), "Case-insensitive material/PNG name collision")
        targets = []
        for src, spec in mapping.items():
            keys(spec, {"name", "base_color_node", "toon_node"}, {"name"})
            mat, dst = materials[src], spec["name"]
            node = base_node(mat, spec.get("base_color_node"))
            if node is not None:
                existing = bpy.data.images.get(dst)
                require(existing is None or existing == node.image, f"Image name already exists: {dst}")
            targets.append((mat, node, dst))
        for mat, node, dst in targets:
            mat.name = "MMDCLI_" + uuid.uuid4().hex
        for mat, node, dst in targets:
            mat.name = dst
            if node is not None:
                if node.image.name != dst:
                    node.image = node.image.copy()
                    node.image.name = dst
                require(node.image.name == dst, f"Image rename failed: {dst}")
        base_images = [node.image.as_pointer() for _, node, _ in targets if node is not None]
        require(len(base_images) == len(set(base_images)), "Base image is still shared by renamed materials")
        toons = []
        if op.get("tidy_toon", True):
            for src, spec in mapping.items():
                mat = materials[src]
                if not mat.node_tree:
                    continue
                candidates = [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image
                              and (n.name == spec.get("toon_node", "mmd_toon_tex") or n.label == "Mmd Toon Tex")]
                require(len(candidates) <= 1, f"Ambiguous toon node: {mat.name}")
                if candidates and candidates[0].image.users == 1:
                    image, target = candidates[0].image, spec["name"] + "_toon"
                    require(bpy.data.images.get(target) in (None, image), f"Toon image name collision: {target}")
                    image.name = target
                    toons.append(target)
        return {"renamed": names, "toon_renamed": toons,
                "no_base_texture": [dst for _, node, dst in targets if node is None]}


def validate_rename(mapping, existing):
    require(isinstance(mapping, dict) and all(isinstance(k, str) and isinstance(v, str) and v for k, v in mapping.items()), "Invalid rename mapping")
    require(set(mapping) <= existing, f"Rename source missing: {sorted(set(mapping) - existing)}")
    require(len(set(mapping.values())) == len(mapping), "Duplicate rename destinations")
    require(not (set(mapping.values()) - set(mapping)) & existing, "Rename destination already exists")


def base_node(mat, explicit=None):
    if not mat.node_tree:
        require(explicit is None, f"Material has no nodes: {mat.name}")
        return None
    if explicit is not None:
        node = mat.node_tree.nodes.get(explicit)
        require(node and node.type == "TEX_IMAGE" and node.image, f"Invalid base image node: {mat.name}/{explicit}")
        return node
    outputs = [n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output]
    if outputs and outputs[0].inputs["Surface"].is_linked:
        shader = outputs[0].inputs["Surface"].links[0].from_node
        if shader.type == "BSDF_PRINCIPLED":
            color = shader.inputs["Base Color"]
            if not color.is_linked:
                return None
            node = color.links[0].from_node
            require(node.type == "TEX_IMAGE" and node.image, f"Specify base_color_node for complex shader: {mat.name}")
            return node
    require(not any(n.type == "TEX_IMAGE" and n.image for n in mat.node_tree.nodes),
            f"Specify base_color_node or convert to Principled first: {mat.name}")
    return None


def save_blend(path):
    versions = bpy.context.preferences.filepaths.save_version
    try:
        bpy.context.preferences.filepaths.save_version = 0
        finished(bpy.ops.wm.save_as_mainfile(filepath=str(path), relative_remap=True))
    finally:
        bpy.context.preferences.filepaths.save_version = versions
    require(path.is_file() and path.stat().st_size > 0, f"Blend save failed: {path}")


def evaluated_coords(mesh):
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [mesh.matrix_world @ vertex.co for vertex in evaluated.data.vertices]


def parse_pose(value):
    name, axis, degrees = value.rsplit(":", 2)
    require(axis.upper() in {"X", "Y", "Z"}, "Pose axis must be X, Y or Z")
    angle = float(degrees)
    require(math.isfinite(angle) and 0 < abs(angle) <= 90, "Pose angle must be nonzero and within ±90 degrees")
    return name, "XYZ".index(axis.upper()), math.radians(angle)


def pose_test(rig, value, callback=None):
    name, axis, angle = parse_pose(value)
    bone = rig.arm.pose.bones.get(name)
    require(bone is not None, f"Pose bone missing: {name}")
    require(not rig.arm.animation_data or not rig.arm.animation_data.action, "Pose testing animated rigs is not supported")
    require(not any(pb.constraints for pb in rig.arm.pose.bones), "Clear constraints before numerical pose tests")
    original_mode, original_basis = bone.rotation_mode, bone.matrix_basis.copy()
    bpy.context.view_layer.update()
    before = [evaluated_coords(o) for o in rig.meshes]
    try:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler[axis] += angle
        bpy.context.view_layer.update()
        after = [evaluated_coords(o) for o in rig.meshes]
        require(all(len(a) == len(b) for a, b in zip(before, after)), "Pose changed evaluated vertex count")
        displacement = max(((a - b).length for group_a, group_b in zip(before, after)
                            for a, b in zip(group_a, group_b)), default=0)
        require(math.isfinite(displacement) and displacement > 1e-8, f"Pose produced no measurable deformation: {name}")
        if callback:
            callback()
    finally:
        bone.rotation_mode = original_mode
        bone.matrix_basis = original_basis
        bpy.context.view_layer.update()
    restored = [evaluated_coords(o) for o in rig.meshes]
    error = max(((a - b).length for group_a, group_b in zip(before, restored)
                 for a, b in zip(group_a, group_b)), default=0)
    require(error < 1e-6, f"Pose did not restore original mesh: {name}, error {error}")
    return {"pose": value, "max_displacement": displacement, "restore_error": error,
            "visual_quality_verified": False}


def export_textures(rig, output):
    images = {n.image.as_pointer(): n.image for mat in rig.used_materials().values() if mat.node_tree
              for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image}
    paths, names = [], set()
    for image in images.values():
        require(image.source in {"FILE", "GENERATED"} and not image.library,
                f"Unsupported image source/library: {image.name}/{image.source}")
        stem = image.name
        while Path(stem).suffix.lower() in {".png", ".bmp", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".webp", ".exr"}:
            stem = str(Path(stem).with_suffix(""))
        require(stem and not any(c in stem for c in '/\\\x00') and stem not in {".", ".."}, f"Unsafe image filename: {image.name}")
        filename = stem + ".png"
        require(filename.casefold() not in names, f"PNG filename collision: {filename}")
        names.add(filename.casefold())
        require(image.size[0] > 0 and image.size[1] > 0, f"Image has no pixels: {image.name}")
        paths.append((image, filename))
    directory = output / "tex"
    directory.mkdir()
    for image, filename in paths:
        image.file_format = "PNG"
        image.filepath_raw = str(directory / filename)
        image.save()
        require((directory / filename).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG output: {filename}")
        image.filepath = "//tex/" + filename
    return [str(directory / filename) for _, filename in paths]


def render_images(rig, job, output):
    scene = bpy.context.scene
    original_camera = scene.camera
    camera = bpy.data.objects.new("MMD_CLI_Camera", bpy.data.cameras.new("MMD_CLI_Camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device, scene.cycles.samples = "CPU", 16
    scene.render.resolution_x = scene.render.resolution_y = job.get("resolution", 512)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("MMD_CLI_World")
    # This command does not save the scene; original lighting is replaced only in memory.
    scene.world.use_nodes = True
    backgrounds = [n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND"]
    for node in backgrounds:
        node.inputs["Color"].default_value = (0.6, 0.6, 0.6, 1)
        node.inputs["Strength"].default_value = 0.8
    selected = set(rig.meshes)
    for obj in scene.objects:
        if obj.type in {"MESH", "LIGHT"} and obj not in selected:
            obj.hide_render = True
        if obj in selected:
            obj.hide_render = False
    camera.data.type = "ORTHO"
    image_dir = output / "images"
    image_dir.mkdir()
    views = {"front": Vector((0, -1, 0)), "side": Vector((1, 0, 0)),
             "back": Vector((0, 1, 0)), "top": Vector((0, 0, 1))}
    files = []

    def capture(label):
        coords = [v for mesh in rig.meshes for v in evaluated_coords(mesh)]
        require(coords, "No vertices to render")
        minimum = Vector(tuple(min(v[i] for v in coords) for i in range(3)))
        maximum = Vector(tuple(max(v[i] for v in coords) for i in range(3)))
        center = (minimum + maximum) / 2
        extent = max((maximum - minimum).length, 0.01)
        camera.data.ortho_scale = extent * 1.15
        camera.data.clip_start, camera.data.clip_end = extent * 0.001, extent * 20
        for view in job.get("views", ["front", "side"]):
            camera.location = center + views[view] * extent * 3
            camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
            path = image_dir / f"{label}-{view}.png"
            scene.render.filepath = str(path)
            finished(bpy.ops.render.render(write_still=True))
            require(path.is_file() and path.stat().st_size > 0, f"Render failed: {path}")
            files.append(str(path))

    try:
        capture("rest")
        poses = [pose_test(rig, pose, lambda i=i: capture(f"pose-{i:02d}"))
                 for i, pose in enumerate(job.get("pose", []), 1)]
    finally:
        scene.camera = original_camera
        bpy.data.objects.remove(camera, do_unlink=True)
    return {"images": files, "poses": poses, "visual_quality_verified": False}


def skin_snapshot(rig):
    result = {}
    for mesh in rig.meshes:
        groups = {g.index: g.name for g in mesh.vertex_groups if g.name in rig.arm.data.bones}
        result[mesh.name] = {
            "positions": [mesh.matrix_world @ v.co for v in mesh.data.vertices],
            "weights": [{groups[g.group]: g.weight for g in v.groups
                         if g.group in groups and g.weight > 1e-7} for v in mesh.data.vertices],
        }
    return result


def check_skin_roundtrip(expected, rig):
    """Match coincident vertices, allowing FBX splits at UV/normal seams."""
    from mathutils.kdtree import KDTree
    actual = skin_snapshot(rig)
    require(set(actual) == set(expected), "FBX skin mesh names changed")
    results = []
    for name, source in expected.items():
        positions = source["positions"]
        require(positions, f"No geometry on mesh: {name}")
        tree = KDTree(len(positions))
        for index, position in enumerate(positions):
            tree.insert(position, index)
        tree.balance()
        diagonal = Vector(tuple(max(p[i] for p in positions) - min(p[i] for p in positions) for i in range(3))).length
        tolerance = max(diagonal * 1e-5, 1e-7)
        covered, max_error = set(), 0.0
        for position, influences in zip(actual[name]["positions"], actual[name]["weights"]):
            candidates = tree.find_range(position, tolerance)
            matching = []
            for _, index, distance in candidates:
                original = source["weights"][index]
                if all(abs(original.get(b, 0) - influences.get(b, 0)) <= 1e-4 for b in set(original) | set(influences)):
                    matching.append(index)
                    max_error = max(max_error, distance)
            require(matching, f"FBX changed vertex position or bone weights: {name}, {tuple(position)}")
            covered.update(matching)
        require(len(covered) == len(positions), f"FBX dropped source vertices/skin influences: {name}")
        results.append({"mesh": name, "source_vertices": len(positions),
                        "reloaded_vertices": len(actual[name]["positions"]), "max_position_error": max_error,
                        "position_tolerance": tolerance, "weight_tolerance": 1e-4})
    return results


def export_model(rig, job, output):
    required = HUMANOID if job.get("require_humanoid") else set()
    before = rig.verify(required)
    require(before["ok"], f"Pre-export verification failed: {before['errors']}")
    REPORT["verification"] = before
    REPORT["poses"] = [pose_test(rig, pose) for pose in job.get("pose", [])]
    # Export rest state only; a user's non-neutral pose must not be silently baked.
    require(all(abs(pb.matrix_basis[i][j] - (1 if i == j else 0)) < 1e-5
                for pb in rig.arm.pose.bones for i in range(4) for j in range(4)),
            "Reset the rig pose before FBX export")
    blend = output / "converted.blend"
    # Establish the new // base before assigning //tex paths. Remapping those
    # against the input file's directory would point back to the old location.
    save_blend(blend)
    if job.get("textures"):
        REPORT["textures"] = export_textures(rig, output)
        save_blend(blend)
    activate(rig.arm)
    for mesh in rig.meshes:
        mesh.select_set(True)
        mesh.hide_render = False
    fbx = output / "converted.fbx"
    import addon_utils
    addon_utils.enable("io_scene_fbx", default_set=False)
    finished(bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True,
                                     object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                                     bake_anim=False, use_mesh_modifiers=False,
                                     mesh_smooth_type="FACE", path_mode="RELATIVE"))
    require(fbx.is_file() and fbx.stat().st_size > 0, "FBX export failed")
    expected_bones = set(rig.arm.data.bones.keys())
    expected = {o.name: mesh_signature(o) for o in rig.meshes}
    expected_skin = skin_snapshot(rig)
    finished(bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False, use_scripts=False))
    reopened = Rig()
    require(expected == {o.name: mesh_signature(o) for o in reopened.meshes}, "Blend roundtrip changed geometry/shape keys")
    blend_check = reopened.verify(required)
    require(blend_check["ok"], f"Saved blend verification failed: {blend_check['errors']}")
    # Remove datablocks as well as objects so reload cannot reuse old images or
    # create .001 material names because the original material is still resident.
    finished(bpy.ops.wm.read_factory_settings(use_empty=True))
    addon_utils.enable("io_scene_fbx", default_set=False)
    finished(bpy.ops.import_scene.fbx(filepath=str(fbx), use_anim=False))
    imported = Rig()
    require(set(imported.arm.data.bones.keys()) == expected_bones, "FBX roundtrip changed bone names/count")
    after = imported.verify(required)
    REPORT["fbx_roundtrip"] = after
    require(after["ok"], f"FBX roundtrip verification failed: {after['errors']}")
    REPORT["skin_roundtrip"] = check_skin_roundtrip(expected_skin, imported)
    # FBX can split vertices along UV/normal boundaries. Compare polygons and shape names, not raw vertex count.
    old_meshes = {m["name"]: m for m in before["meshes"]}
    new_meshes = {m["name"]: m for m in after["meshes"]}
    require(set(old_meshes) == set(new_meshes), "FBX roundtrip changed model mesh names/count")
    for name, original in old_meshes.items():
        reloaded = new_meshes[name]
        require(original["polygons"] == reloaded["polygons"]
                and set(original["shape_keys"][1:]) == set(reloaded["shape_keys"][1:])
                and len(original["uv_layers"]) == len(reloaded["uv_layers"])
                and original["used_materials"] == reloaded["used_materials"],
                f"FBX data retention failed: {name}; before={original}; after={reloaded}")
    return {"blend": str(blend), "fbx": str(fbx), "blend_roundtrip": blend_check,
            "fbx_roundtrip": after, "motionbuilder_verified": False}


def apply_plan(job, output):
    plan = job["plan"]
    keys(plan, {"version", "input_sha256", "armature", "meshes", "operations", "required_bones", "pose_tests"},
         {"version", "input_sha256", "armature", "meshes", "operations"})
    require(plan["version"] == 1, "Unsupported plan version")
    require(plan["input_sha256"] == job["input_sha256"], "Plan does not match input")
    for op in plan["operations"]:
        kind = op.get("type")
        require(kind in OPS, f"Unknown operation: {kind}")
        keys(op, OPS[kind] | {"type"})
    material_only = plan["armature"] is None
    if material_only:
        require(all(op["type"] in {"principled_materials", "rename_materials"} for op in plan["operations"]),
                "armature:null only supports material operations")
        require(not plan.get("pose_tests") and not plan.get("required_bones"), "Material-only plan cannot test bones")
    rig = Rig(plan["armature"], plan["meshes"], material_only=material_only)
    checkpoints = output / "checkpoints"
    if not job.get("dry_run"):
        checkpoints.mkdir()
        save_blend(checkpoints / "000-input.blend")
    REPORT["operations"] = []
    for index, op in enumerate(plan["operations"], 1):
        result = getattr(rig, op["type"])(op)
        bpy.context.view_layer.update()
        verification = rig.verify()
        REPORT["operations"].append({"index": index, "type": op["type"], "result": result,
                                     "verification": verification})
        require(verification["ok"], f"Post-operation verification failed: {verification['errors']}")
        if not job.get("dry_run"):
            checkpoint = checkpoints / f"{index:03d}-{op['type']}.blend"
            save_blend(checkpoint)
            REPORT["operations"][-1]["checkpoint"] = str(checkpoint)
    verification = rig.verify(plan.get("required_bones", []))
    REPORT["verification"] = verification
    require(verification["ok"], f"Final plan verification failed: {verification['errors']}")
    REPORT["poses"] = [pose_test(rig, pose) for pose in plan.get("pose_tests", [])]
    if not job.get("dry_run"):
        save_blend(output / "converted.blend")
        REPORT["blend"] = str(output / "converted.blend")
    REPORT["scene"] = scene_info()


def main(job, output):
    load_input(job)
    if job["command"] == "inspect":
        REPORT["scene"] = scene_info()
    elif job["command"] == "apply":
        apply_plan(job, output)
    else:
        rig = Rig(job.get("armature"), job.get("meshes"))
        verification = rig.verify(HUMANOID if job.get("require_humanoid") else set())
        REPORT["verification"] = verification
        require(verification["ok"], f"Verification failed: {verification['errors']}")
        if job["command"] == "verify":
            REPORT["poses"] = [pose_test(rig, pose) for pose in job.get("pose", [])]
        elif job["command"] == "render":
            REPORT.update(render_images(rig, job, output))
        elif job["command"] == "export":
            REPORT.update(export_model(rig, job, output))
    REPORT["ok"] = True


if __name__ == "__main__":
    request = Path(sys.argv[sys.argv.index("--") + 1])
    JOB = json.loads(request.read_text(encoding="utf-8"))
    OUT = Path(JOB["output_dir"])
    REPORT = {"ok": False, "command": JOB["command"], "input": JOB["input"],
              "input_sha256": JOB["input_sha256"], "blender_version": bpy.app.version_string,
              "background": bpy.app.background, "dry_run": JOB.get("dry_run", False)}
    try:
        require(bpy.app.background, "Worker must run in background mode")
        main(JOB, OUT)
    except Exception:
        REPORT["error"] = traceback.format_exc()
        raise
    finally:
        (OUT / "report.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
