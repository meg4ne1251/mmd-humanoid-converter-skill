"""Create a redistributable synthetic rig; no user model is used by tests."""
from pathlib import Path
import sys

import bpy


out = Path(sys.argv[sys.argv.index("--") + 1])
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
parent = bpy.data.objects.new("ImportRoot", None)
bpy.context.collection.objects.link(parent)
parent.location.x = 0.25
arm = bpy.data.objects.new("Rig", bpy.data.armatures.new("Rig"))
bpy.context.collection.objects.link(arm)
arm.parent = parent
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for name, head, tail, ancestor in [
    ("Root", (0, 0, 1), (0, 0, 2), None),
    ("Helper", (0, 0, 2), (0, 0, 3), "Root"),
    ("Tip", (0, 0, 3), (0, 0, 3.1), "Helper"),
    ("_shadow", (0, 0, 0), (0, 0, 0.1), None),
]:
    bone = arm.data.edit_bones.new(name)
    bone.head, bone.tail = head, tail
    bone.parent = arm.data.edit_bones.get(ancestor) if ancestor else None
bpy.ops.object.mode_set(mode="OBJECT")
arm.pose.bones["Root"].constraints.new("COPY_ROTATION")
data = bpy.data.meshes.new("Body")
data.from_pydata([(0, 0, 1), (1, 0, 1), (0, 0, 2), (2, 0, 1), (3, 0, 1), (2, 0, 2)], [], [(0, 1, 2), (3, 4, 5)])
mesh = bpy.data.objects.new("Body", data)
bpy.context.collection.objects.link(mesh)
mesh.parent = parent
mesh.shape_key_add(name="Basis")
for name in ["あ", "い", "う", "え", "お"]:
    key = mesh.shape_key_add(name=name)
    key.data[2].co.x += 0.1
for name, value in [("Root", 0.25), ("Helper", 0.75)]:
    mesh.vertex_groups.new(name=name).add(list(range(6)), value, "REPLACE")
mesh.vertex_groups.new(name="_shadow")
mesh.modifiers.new("Armature", "ARMATURE").object = arm
mesh.data.uv_layers.new(name="UVMap")
image = bpy.data.images.new("Source", width=8, height=8)
image.generated_color = (0.2, 0.7, 0.4, 1)
image.filepath_raw = str(out / "source.png")
image.file_format = "PNG"
image.save()
for name in ["OldFace", "OldClothes"]:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    base = material.node_tree.nodes.new("ShaderNodeTexImage")
    base.name = "base"
    base.image = image
    uv = material.node_tree.nodes.new("ShaderNodeUVMap")
    material.node_tree.links.new(uv.outputs["UV"], base.inputs["Vector"])
    mesh.data.materials.append(material)
mesh.data.polygons[1].material_index = 1
bpy.ops.wm.save_as_mainfile(filepath=str(out / "source.blend"))
# A standalone, unrigged model exercises the material-only plan path.
bpy.data.objects.remove(arm, do_unlink=True)
for modifier in list(mesh.modifiers):
    mesh.modifiers.remove(modifier)
bpy.ops.wm.save_as_mainfile(filepath=str(out / "unrigged.blend"))

# PMX test is optional: ordinary .blend editing does not require MMD Tools.
import addon_utils
import importlib
modules = [m.__name__ for m in addon_utils.modules() if m.__name__ == "mmd_tools" or m.__name__.endswith(".mmd_tools")]
if len(modules) == 1:
    pmx = importlib.import_module(modules[0] + ".core.pmx")
    model = pmx.Model()
    model.name = model.name_e = "SyntheticPMX"
    bone = pmx.Bone()
    bone.name = bone.name_e = "Root"
    bone.location, bone.parent, bone.displayConnection = [0.0, 0.0, 0.0], -1, [0.0, 1.0, 0.0]
    model.bones = [bone]
    for co in [(0, 0, 0), (1, 0, 0), (0, 1, 0)]:
        vertex = pmx.Vertex()
        vertex.co, vertex.normal = co, [0.0, 0.0, 1.0]
        vertex.weight = pmx.BoneWeight()
        vertex.weight.bones = [0]
        model.vertices.append(vertex)
    material = pmx.Material()
    material.name = material.name_e = "Material"
    material.diffuse = [1.0, 1.0, 1.0, 1.0]
    material.specular = material.ambient = [0.0, 0.0, 0.0]
    material.edge_color = [0.0, 0.0, 0.0, 1.0]
    material.vertex_count = 3
    model.materials, model.faces = [material], [(0, 1, 2)]
    pmx.save(str(out / "synthetic.pmx"), model)
