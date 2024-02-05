# Create PlayStation 1 shaders for PS1 model rips.
# Usage: Run script with imported PS1 models selected.
# Tested with: Blender 3.6, 4.0, 4.1

import bpy


def ps1ify_material(mesh, material):
    nodes = [] if not material.node_tree else material.node_tree.nodes
    img_nodes = [n for n in nodes if n.type == 'TEX_IMAGE' and n.image]
    image = img_nodes[0].image if img_nodes else None

    vertex_color = '' if mesh.color_attributes else None

    semitransparent = 'transparent' in material.name.lower()

    setup_ps1_material(
        material,
        image=image,
        vertex_color=vertex_color,
        use_semitransparent_mode0=semitransparent,
    )
    material.use_backface_culling = False
    material.blend_method = 'HASHED' if not semitransparent else 'BLEND'


# Overview of PS1 fragment processing (AIUI):
#
#  * Polygons may be textured/untextured and colored/uncolored.
#  * When using both texture and vertex color, they are combined
#    with 2 * vertexColor * textureColor.
#  * Textures use nearest neighbor (pixelated) filtering.
#  * Textures and vertex colors do not have alpha channels.
#    Instead...
#  * Black (#000) texels are treated as fully transparent. (We
#    assume this fact is already baked into the textures.)
#  * When semi-transparency mode 0 is enabled, the background
#    and foreground are combined with B/2+F/2, ie. blended with
#    alpha=50%. Other semi-transparency modes are not supported
#    because they aren't subsets of alpha blending.

def setup_ps1_material(
    material,
    image,
    vertex_color=None,  # vertex color attribute name ('' = default)
    use_texture_alpha=True,
    use_semitransparent_mode0=False,
):
    if not image:
        use_texture_alpha = False
    use_alpha = use_texture_alpha or use_semitransparent_mode0
    use_color = vertex_color is not None

    if not image and not use_color:
        return

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    nodes.clear()
    node_out = nodes.new('ShaderNodeOutputMaterial')

    # Texture / Vertex Color

    if use_color:
        node_color = nodes.new('ShaderNodeVertexColor')
        node_color.layer_name = vertex_color
    if image:
        node_img = nodes.new('ShaderNodeTexImage')
        node_img.image = image
        node_img.interpolation = 'Closest'

    if image and not use_color:
        color_socket = node_img.outputs['Color']

        node_img.location = -400, 100

    elif not image and use_color:
        color_socket = node_color.outputs['Color']

        node_color.location = -300, 80

    else:
        # Vertex color and texture color are combined with
        #
        #   outputColor = 2 * vertexColor * textureColor
        #
        # This is done in sRGB. In the Blender shader, the colors have been
        # converted to linear. The equivalent in linear is approximately
        #
        #   outputColor = 4.6 * vertexColor * textureColor

        # Multiply vertex color by 2
        node_2x = nodes.new('ShaderNodeVectorMath')
        node_2x.label = 'Multiply x 2'
        node_2x.operation = 'MULTIPLY'
        node_2x.inputs[1].default_value = [4.63262] * 3
        links.new(node_color.outputs['Color'], node_2x.inputs[0])

        # Multiply with texture color
        node_mul = nodes.new('ShaderNodeMix')
        node_mul.data_type = 'RGBA'
        node_mul.blend_type = 'MULTIPLY'
        node_mul.clamp_result = True
        node_mul.inputs[0].default_value = 1                      # Fac
        links.new(node_img.outputs['Color'], node_mul.inputs[6])  # Color A
        links.new(node_2x.outputs[0], node_mul.inputs[7])         # Color B

        color_socket = node_mul.outputs[2]

        node_mul.location = -300, 40
        node_img.location = -700, 200
        node_2x.location = -600, -200
        node_color.location = -800, -200

    # Alpha

    if not use_alpha:
        links.new(color_socket, node_out.inputs[0])

        node_out.location = 20, 20

    else:
        node_alpha = nodes.new('ShaderNodeMixShader')
        node_transp = nodes.new('ShaderNodeBsdfTransparent')
        links.new(node_transp.outputs[0], node_alpha.inputs[1])
        links.new(node_alpha.outputs[0], node_out.inputs[0])
        links.new(color_socket, node_alpha.inputs[2])

        node_alpha.location = 20, 200
        node_transp.location = -300, 400
        node_out.location = 250, 260

    if use_texture_alpha and not use_semitransparent_mode0:
        links.new(node_img.outputs['Alpha'], node_alpha.inputs[0])

    elif not use_texture_alpha and use_semitransparent_mode0:
        node_alpha.inputs[0].default_value = 0.5

    elif use_texture_alpha and use_semitransparent_mode0:
        # Alpha = TextureAlpha * 0.5
        node_amul = nodes.new('ShaderNodeMath')
        node_amul.operation = 'MULTIPLY'
        links.new(node_img.outputs['Alpha'], node_amul.inputs[0])
        node_amul.inputs[1].default_value = 0.5
        links.new(node_amul.outputs[0], node_alpha.inputs[0])

        node_amul.location = -300, 250
        if not use_color:
            node_img.location = -650, 0


def set_color_management():
    # Turn off default Filmic color management, which darkens color.
    # See eg: https://blender.stackexchange.com/questions/164677
    bpy.context.scene.display_settings.display_device = 'sRGB'
    bpy.context.scene.view_settings.view_transform = 'Standard'
    bpy.context.scene.sequencer_colorspace_settings.name = 'sRGB'


if __name__ == '__main__':
    obs = bpy.context.selected_objects or bpy.data.objects
    for ob in obs:
        if ob.type != 'MESH': continue
        for mat in ob.data.materials:
            if not mat: continue
            ps1ify_material(ob.data, mat)
    set_color_management()
