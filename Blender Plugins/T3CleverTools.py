bl_info = {
    "name": "T3CleverTools",
    "author": "T3-ModTools",
    "version": (0, 2, 0),
    "blender": (3, 6, 0),
    "location": "Properties > Material > T3CleverTools; View3D > Sidebar > T3",
    "description": "Edit T3 material self-illumination and transparency for SCA and LOD export",
    "category": "Material",
}

import bpy
from bpy.props import BoolProperty, FloatProperty


def shader_type(material):
    return str(material.get("t3_shader_type", "")).strip().upper()


def get_emissive(material):
    # Names such as 'sillum' are not sufficient: the native shader is the source
    # of truth. Both T3 glTF and LOD importers preserve this material metadata.
    return shader_type(material) == "BASE"


def owned_node(material, role):
    if material.node_tree:
        return next((n for n in material.node_tree.nodes
                     if n.get("t3_clever_role") == role), None)
    return None


def update_emission_preview(material):
    """Reversible preview wrapper; preserve the original surface and textures."""
    enabled = get_emissive(material)
    if enabled:
        material.use_nodes = True
    if not material.use_nodes or not material.node_tree:
        return False
    tree = material.node_tree
    output = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if output is None:
        return False
    surface = output.inputs.get("Surface")
    mix = owned_node(material, "surface_wrapper")
    emission = owned_node(material, "emission")
    if not enabled:
        if mix:
            # Only restore destinations still using our wrapper. Never replace
            # a connection the artist has edited after enabling the preview.
            previous = mix.inputs[1].links[0].from_socket if mix.inputs[1].is_linked else None
            destinations = [link.to_socket for link in mix.outputs[0].links]
            if previous:
                for destination in destinations:
                    tree.links.new(previous, destination)
            tree.nodes.remove(mix)
        if emission:
            tree.nodes.remove(emission)
        return True
    if mix:
        return True
    # A Principled surface is the supported preview contract. The export flag
    # also works for custom node graphs; do not rewrite those graphs by guesswork.
    if not surface or not surface.is_linked:
        return False
    previous = surface.links[0].from_socket
    principled = previous.node
    if principled.type != "BSDF_PRINCIPLED":
        return False
    color = principled.inputs.get("Base Color")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission["t3_clever_role"] = "emission"
    emission.label = "T3CleverTools · Autoiluminación"
    emission.inputs["Strength"].default_value = 1.0
    if color.is_linked:
        tree.links.new(color.links[0].from_socket, emission.inputs["Color"])
    else:
        emission.inputs["Color"].default_value = color.default_value
    mix = tree.nodes.new("ShaderNodeMixShader")
    mix["t3_clever_role"] = "surface_wrapper"
    mix.label = "T3CleverTools · Vista previa"
    mix.inputs[0].default_value = 1.0
    emission.location = (principled.location.x + 180, principled.location.y - 220)
    mix.location = (output.location.x - 180, output.location.y)
    tree.links.new(previous, mix.inputs[1])
    tree.links.new(emission.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], surface)
    return True


def get_transparency(material):
    return bool(material.get("t3_transparency_enabled", False))


def get_amount(material):
    return float(material.get("t3_transparency_amount", 50.0))


def remove_transparency_preview(material):
    tree = material.node_tree
    mix = owned_node(material, "transparency_wrapper")
    if mix:
        previous = mix.inputs[1].links[0].from_socket if mix.inputs[1].is_linked else None
        if previous:
            for destination in [l.to_socket for l in mix.outputs[0].links]:
                tree.links.new(previous, destination)
        tree.nodes.remove(mix)
    transparent = owned_node(material, "transparent")
    if transparent:
        tree.nodes.remove(transparent)
    for attr in ("surface_render_method", "blend_method"):
        key = "t3_clever_previous_" + attr
        if key in material:
            if hasattr(material, attr):
                setattr(material, attr, material[key])
            del material[key]


def update_preview(material):
    # Unwrap the outer transparency layer before updating the emission layer.
    remove_transparency_preview(material)
    updated = update_emission_preview(material)
    if not get_transparency(material):
        return updated
    material.use_nodes = True
    tree = material.node_tree
    output = next((n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output), None)
    if not output or not output.inputs['Surface'].is_linked:
        return False
    surface = output.inputs['Surface']
    previous = surface.links[0].from_socket
    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
    transparent['t3_clever_role'] = 'transparent'
    mix = tree.nodes.new('ShaderNodeMixShader')
    mix['t3_clever_role'] = 'transparency_wrapper'
    mix.label = 'T3CleverTools · Transparency'
    mix.inputs[0].default_value = max(0.0, min(1.0, get_amount(material) / 100.0))
    tree.links.new(previous, mix.inputs[1])
    tree.links.new(transparent.outputs[0], mix.inputs[2])
    tree.links.new(mix.outputs[0], surface)
    mix.location = (output.location.x - 160, output.location.y)
    transparent.location = (mix.location.x - 160, mix.location.y - 200)
    attr = 'surface_render_method' if hasattr(material, 'surface_render_method') else 'blend_method'
    if hasattr(material, attr):
        material['t3_clever_previous_' + attr] = getattr(material, attr)
        setattr(material, attr, 'DITHERED' if attr == 'surface_render_method' else 'HASHED')
    return True


def set_transparency(material, enabled):
    material['t3_transparency_enabled'] = bool(enabled)
    update_preview(material)


def set_amount(material, value):
    material['t3_transparency_amount'] = max(0.0, min(100.0, value))
    update_preview(material)


def set_emissive(material, enabled):
    before = shader_type(material)
    if enabled:
        if before != "BASE":
            material["t3_clever_unlit_previous_shader"] = before or "DIFFUSE_SPECULAR"
        material["t3_shader_type"] = "BASE"
    else:
        previous = str(material.get("t3_clever_unlit_previous_shader", "DIFFUSE_SPECULAR"))
        material["t3_shader_type"] = previous if previous and previous != "BASE" else "DIFFUSE_SPECULAR"
    update_preview(material)


def model_materials(context):
    obj = context.object
    if obj is None:
        return []
    meshes = [obj] if obj.type == "MESH" else []
    if obj.type == "ARMATURE":
        meshes = [o for o in context.scene.objects if o.type == "MESH" and o.find_armature() == obj]
    seen = set()
    materials = []
    for mesh in meshes:
        for slot in mesh.material_slots:
            mat = slot.material
            if mat is not None and mat.as_pointer() not in seen:
                seen.add(mat.as_pointer())
                materials.append(mat)
    return materials


def draw_material(layout, material):
    box = layout.box()
    box.label(text=material.name, icon="MATERIAL")
    editable = material.is_editable
    row = box.row()
    row.enabled = editable
    row.prop(material, "t3_clever_emissive", text="Autoiluminación (sillum)")
    column = box.column()
    column.enabled = editable
    column.prop(material, 't3_clever_transparency', text='Transparency')
    if get_transparency(material):
        column.prop(material, 't3_clever_transparency_amount', text='Amount (%)')
        column.label(text='0: opaco · 100: transparente')
        column.label(text='Compilar con T3-ModTools actualizado.', icon='INFO')
    if not editable:
        box.label(text="Material vinculado: crea una copia local para editar.", icon="INFO")
    elif not shader_type(material):
        box.label(text="Sin datos T3. Activa la casilla para asignarlos.", icon="INFO")
    if material.users > 1:
        box.label(text="Material compartido: el cambio afecta a sus usuarios.", icon="LINKED")
    texture = str(material.get("t3_base_texture", ""))
    if texture:
        box.label(text="Textura: " + texture, icon="IMAGE_DATA")


class T3CLEVER_OT_preview(bpy.types.Operator):
    bl_idname = "material.t3_clever_preview"
    bl_label = "Actualizar vista previa"
    bl_description = "Actualizar la vista previa de autoiluminación y transparencia T3"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        materials = ([context.material] if getattr(context, "material", None)
                     else model_materials(context))
        updated = sum(update_preview(m) for m in materials if m.is_editable)
        self.report({"INFO"}, f"Vista previa actualizada: {updated}/{len(materials)} materiales")
        return {"FINISHED"}


class T3CLEVER_PT_material(bpy.types.Panel):
    bl_label = "T3CleverTools"
    bl_idname = "T3CLEVER_PT_material"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        draw_material(self.layout, context.material)
        self.layout.operator(T3CLEVER_OT_preview.bl_idname, icon="SHADING_RENDERED")
        self.layout.label(text="Exportación: T3 Model (.sca) / T3 LOD (.lod)")


class T3CLEVER_PT_model(bpy.types.Panel):
    bl_label = "T3CleverTools"
    bl_idname = "T3CLEVER_PT_model"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "T3"

    def draw(self, context):
        materials = model_materials(context)
        if not materials:
            self.layout.label(text="Selecciona una malla o su armature.", icon="INFO")
            self.layout.label(text="La malla debe tener un material asignado.")
            return
        for mat in materials:
            draw_material(self.layout, mat)
        self.layout.operator(T3CLEVER_OT_preview.bl_idname, icon="SHADING_RENDERED")
        self.layout.label(text="Autoiluminación del material; no crea luces.")
        self.layout.label(text="Exporta con T3 Model (.sca) / T3 LOD (.lod).")


CLASSES = (T3CLEVER_OT_preview, T3CLEVER_PT_material, T3CLEVER_PT_model)


def register():
    bpy.types.Material.t3_clever_transparency = BoolProperty(
        name='Transparency', description='Transparencia gradual para T3-ModTools',
        get=get_transparency, set=set_transparency)
    bpy.types.Material.t3_clever_transparency_amount = FloatProperty(
        name='Amount (%)', description='0 = opaco; 100 = totalmente transparente',
        min=0, max=100, precision=1, get=get_amount, set=set_amount)
    bpy.types.Material.t3_clever_emissive = BoolProperty(
        name="Autoiluminación (sillum)",
        description="Autoiluminación T3 como los ojos del T900. Se guarda en SCA/LOD; no crea una luz dinámica",
        get=get_emissive, set=set_emissive,
    )
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.Material.t3_clever_emissive
    del bpy.types.Material.t3_clever_transparency
    del bpy.types.Material.t3_clever_transparency_amount


if __name__ == "__main__":
    register()
