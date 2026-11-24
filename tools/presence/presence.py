"""Build the editable ARTEMIS Presence loop in Blender."""

import argparse
from math import cos, pi, radians, sin, tau
from pathlib import Path
from random import Random
import sys

import bpy
from mathutils import Vector


FPS = 24
FRAMES = 144
PALETTE = {
    "Ciano": ((0.08, 0.68, 1.0), 1.10),
    "Azul frio": ((0.07, 0.26, 0.94), 0.34),
    "Violeta": ((0.46, 0.22, 0.99), 0.45),
    "Branco gelo": ((0.44, 0.87, 1.0), 1.62),
}


def emission(name, color, strength):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    emitter = nodes.new("ShaderNodeEmission")
    emitter.inputs["Color"].default_value = (*color, 1)
    emitter.inputs["Strength"].default_value = strength
    output = nodes.new("ShaderNodeOutputMaterial")
    material.node_tree.links.new(emitter.outputs[0], output.inputs["Surface"])
    return material


def rotor(name, tilt):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.rotation_euler = tuple(radians(angle) for angle in tilt)
    return obj


def traces(name, parent, paths, radius, material, *, taper=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 0
    curve.resolution_u = 1
    for path in paths:
        spline = curve.splines.new("POLY")
        spline.points.add(len(path) - 1)
        for i, (point, position) in enumerate(zip(spline.points, path)):
            point.co = (*position, 1)
            if taper:
                point.radius = max(0.035, sin(pi * i / (len(path) - 1)) ** 1.6)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    curve.materials.append(material)


def wisps(rng, materials):
    # Layer curved strands along a shared flow so the field reads as one form.
    for layer, (name, tilt, orbit_speed) in enumerate((
        ("Véu externo", (48, -25, 18), 1),
        ("Fluxo central", (-30, 34, -22), -1),
        ("Véu violeta", (22, 59, 42), 1),
        ("Pulso interno", (30, -18, 34), -1),
    )):
        group = rotor(name, tilt)
        strands = []
        for i in range(5 if layer != 3 else 3):
            bundle = i % 3
            phase = bundle * tau / 3 + rng.uniform(-0.23, 0.23)
            reach = rng.uniform(1.1, 1.66) * (0.60 if layer == 3 else 1)
            wave = rng.uniform(0.75, 1.25)
            strand = []
            for j in range(80):
                u = j / 79
                envelope = sin(pi * u) ** 1.26
                radial = 0.06 + reach * envelope
                angle = phase + 4.8 * u + 0.39 * sin(tau * u + layer)
                strand.append((
                    radial * cos(angle),
                    radial * sin(angle),
                    (u - 0.5) * 0.88 + 0.64 * envelope * sin(wave * tau * u + phase),
                ))
            strands.append(strand)
        traces(name + " · filamentos", group, strands, 0.0038, materials["Violeta" if layer == 2 else "Azul frio"], taper=True)
        base = group.rotation_euler.copy()
        for n in range(25):
            phase = tau * n / 24
            group.rotation_euler = (
                base.x + 0.23 * sin(phase + layer),
                base.y + 0.21 * sin(phase * 2),
                base.z + orbit_speed * phase,
            )
            expansion = 1 + 0.09 * sin(phase * 2 + layer * 0.65)
            group.scale = (expansion, 1 / expansion, 1)
            frame = 1 + FRAMES * n // 24
            group.keyframe_insert(data_path="rotation_euler", frame=frame)
            group.keyframe_insert(data_path="scale", frame=frame)


def mist():
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=2.0)
    cloud = bpy.context.object
    cloud.name = "Névoa de luz volumétrica"
    material = bpy.data.materials.new("Névoa azul-violeta")
    material.use_nodes = True
    cloud.data.materials.append(material)
    tree = material.node_tree
    tree.nodes.clear()
    coordinate = tree.nodes.new("ShaderNodeTexCoord")
    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 4.4
    distance = tree.nodes.new("ShaderNodeVectorMath")
    distance.operation = "DISTANCE"
    distance.inputs[1].default_value = (0.5, 0.5, 0.5)
    fade = tree.nodes.new("ShaderNodeMapRange")
    fade.inputs["From Max"].default_value = 0.5
    fade.inputs["To Min"].default_value = 1
    fade.inputs["To Max"].default_value = 0
    fade.interpolation_type = "SMOOTHERSTEP"
    intensity = tree.nodes.new("ShaderNodeMath")
    intensity.operation = "MULTIPLY"
    gain = tree.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 1.65
    volume = tree.nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Density"].default_value = 0
    volume.inputs["Emission Color"].default_value = (0.013, 0.095, 0.34, 1)
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    for source, destination in (
        (coordinate.outputs["Generated"], noise.inputs["Vector"]),
        (coordinate.outputs["Generated"], distance.inputs[0]),
        (distance.outputs["Value"], fade.inputs["Value"]),
        (fade.outputs["Result"], intensity.inputs[0]),
        (noise.outputs["Fac"], intensity.inputs[1]),
        (intensity.outputs[0], gain.inputs[0]),
        (gain.outputs[0], volume.inputs["Emission Strength"]),
        (volume.outputs[0], output.inputs["Volume"]),
    ):
        tree.links.new(source, destination)
    for frame, scale in ((1, 0.94), (73, 1.05), (145, 0.94)):
        cloud.scale = (scale, scale, scale)
        cloud.keyframe_insert(data_path="scale", frame=frame)


def impulses(rng, materials):
    graph = rotor("Sinapses · sinais em cascata", (8, -16, 7))
    tracks = []
    for arm in range(5):
        theta = arm * tau / 5 + rng.uniform(-0.24, 0.24)
        direction = Vector((cos(theta), sin(theta), rng.uniform(-0.44, 0.44)))
        origin = direction * 0.12
        node = direction * rng.uniform(0.68, 0.90)
        delay = 8 + arm * 9
        branches = [(origin, node, delay)]
        for side in (-1, 1):
            branch = Vector((cos(theta + side * 0.38), sin(theta + side * 0.38), rng.uniform(-0.6, 0.6)))
            branches.append((node + branch * 0.047, branch * rng.uniform(1.39, 1.89), delay + 13 + (side == 1) * 4))
        for start, end, start_frame in branches:
            bend = Vector((-sin(theta), cos(theta), rng.uniform(-1, 1))) * rng.uniform(-0.23, 0.23)
            path = [start.lerp(end, i / 16) + bend * sin(pi * i / 16) for i in range(17)]
            tracks.append(path)
            for offset, size in ((0, 0.032), (2, 0.020), (4, 0.012)):
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=size)
                spark = bpy.context.object
                spark.name = "Impulso · " + str(arm + 1)
                spark.parent = graph
                spark.data.materials.append(materials["Branco gelo" if offset == 0 else "Ciano"])
                spark.location = path[0]
                spark.scale = (0, 0, 0)
                spark.keyframe_insert(data_path="scale", frame=1)
                for cycle in (0, 68):
                    beginning = start_frame + offset + cycle
                    for i, location in enumerate(path):
                        frame = beginning + i * 0.75
                        spark.location = location
                        scale = sin(pi * i / 16) ** 0.34 if 0 < i < 16 else 0
                        spark.scale = (scale,) * 3
                        spark.keyframe_insert(data_path="location", frame=frame)
                        spark.keyframe_insert(data_path="scale", frame=frame)
                spark.location = path[0]
                spark.keyframe_insert(data_path="location", frame=1)
                spark.keyframe_insert(data_path="location", frame=145)
                spark.keyframe_insert(data_path="scale", frame=145)
    traces("Ramificações latentes", graph, tracks, 0.0038, materials["Azul frio"], taper=True)


def artwork_presence(scene, artwork):
    """Place the supplied design in camera space and animate its existing signals."""
    image = bpy.data.images.load(str(artwork.resolve()), check_existing=False)
    image.pack()
    width, height = image.size
    bpy.ops.mesh.primitive_plane_add(size=5)
    plate = bpy.context.object
    plate.name = "Imagem de referência · incorporada"
    plate.scale.x = width / max(width, height)
    plate.scale.y = height / max(width, height)
    material = emission("Arte base", (1, 1, 1), 1)
    plate.data.materials.append(material)
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    emitter = next(node for node in material.node_tree.nodes if node.type == "EMISSION")
    material.node_tree.links.new(texture.outputs["Color"], emitter.inputs["Color"])
    scene.view_settings.view_transform = "Standard"
    camera = scene.camera
    camera.location = (0, 0, 10)
    camera.rotation_euler = (0, 0, 0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 5

    def surface(x, y):
        return Vector(((x / 1254 - 0.5) * 5 * plate.scale.x,
                       (0.5 - y / 1254) * 5 * plate.scale.y, 0.06))

    materials = {
        "ciano": emission("Disparo ciano", (0.08, 0.54, 1.0), 8),
        "violeta": emission("Disparo violeta", (0.45, 0.12, 1.0), 8),
        "gelo": emission("Junção elétrica", (0.52, 0.84, 1.0), 12),
    }

    def spark(name, size, color, points, schedule):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=size)
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(materials[color])
        initial = surface(*points[0])
        for frame in (1, FRAMES + 1):
            obj.location = initial
            obj.scale = (0, 0, 0)
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="scale", frame=frame)
        for start, finish in schedule:
            for i, point in enumerate(points):
                progress = i / (len(points) - 1)
                frame = start + (finish - start) * progress
                obj.location = surface(*point)
                scale = sin(pi * progress) ** 0.46 if 0 < i < len(points) - 1 else 0
                obj.scale = (scale,) * 3
                obj.keyframe_insert(data_path="location", frame=frame)
                obj.keyframe_insert(data_path="scale", frame=frame)

    center = (635, 603)
    routes = (
        ("Superior esquerdo", (428, 309), "ciano", 9, [(574, 554), (510, 520), (462, 431), (446, 364)]),
        ("Superior direito", (858, 477), "violeta", 25, [(689, 549), (744, 515), (803, 490)]),
        ("Inferior direito", (860, 779), "ciano", 44, [(697, 629), (753, 652), (799, 695), (831, 736)]),
        ("Inferior esquerdo", (350, 773), "violeta", 59, [(548, 608), (477, 621), (425, 671), (388, 723)]),
    )
    for name, junction, color, start, coords in routes:
        path = [center, *coords, junction]
        for lag, size in ((0, 0.021), (2, 0.012)):
            spark("Pulso · " + name, size, color, path,
                  [(start + lag, start + 19 + lag), (start + 49 + lag, start + 68 + lag)])
        spark("Ativação · " + name, 0.041, "gelo", [junction] * 3,
              [(start + 16, start + 26), (start + 65, start + 75)])
    spark("Pulso do núcleo", 0.030, "gelo", [center] * 3, [(5, 21), (51, 70), (104, 123)])


def circuit_presence(scene, seed):
    rng = Random(seed)
    parent = rotor("ARTEMIS · expansão e contração", (0, 0, 0))
    scene.camera.location = (0, 0, 11)
    scene.camera.rotation_euler = (0, 0, 0)
    scene.camera.data.type = "ORTHO"
    scene.camera.data.ortho_scale = 6.55
    scene.view_settings.view_transform = "Standard"
    cyan = emission("Trilhas de dados · ciano", (0.018, 0.41, 1), 1.25)
    purple = emission("Trilhas de dados · violeta", (0.19, 0.042, 1), 1.35)
    faint = emission("Circuito de fundo", (0.009, 0.075, 0.31), 0.73)
    bright = emission("Módulo recebido", (0.21, 0.67, 1), 4.2)
    altered = emission("Dados transformados", (0.43, 0.12, 1), 4.2)

    def polar(radius, angle, z=0):
        return Vector((radius * cos(angle), radius * sin(angle), z))

    def segment(radius, theta, length, z=0):
        return [polar(radius, theta + length * i / 16, z) for i in range(17)]

    thin, cyan_tracks, violet_tracks, links = [], [], [], []
    radii = (0.76, 1.04, 1.29, 1.54, 1.78, 2.02, 2.25, 2.40)
    for ring, radius in enumerate(radii):
        z = 0.19 * cos(ring * 1.42) - 0.1
        for lane in range(4):
            for j in range(14):
                phi = j * tau / 14 + ring * 0.18
                sweep = rng.uniform(0.18, 0.39)
                path = segment(radius + lane * 0.026, phi, sweep, z)
                if lane in (0, 3) and (j + ring) % 3 != 1:
                    (violet_tracks if (j + ring) % 4 == 0 else cyan_tracks).append(path)
                else:
                    thin.append(path)
        for j in range(72):
            phi = j * tau / 72 + ring * 0.12
            if rng.random() < 0.72:
                end = radius - (0.115 if j % 6 == 0 else rng.uniform(0.018, 0.065))
                thin.append([polar(radius, phi, z), polar(end, phi, z)])
        if ring < len(radii) - 1:
            for j in range(11):
                phi = (j + rng.uniform(-0.16, 0.16)) * tau / 11
                links.append([polar(radius, phi, z), polar(radius + 0.13, phi, z),
                              polar(radius + 0.17, phi + 0.025, z),
                              polar(radii[ring + 1], phi + 0.025, z)])
    traces("Pistas da malha", parent, thin, 0.0027, faint)
    traces("Trilhas ciano", parent, cyan_tracks, 0.0042, cyan)
    traces("Trilhas violeta", parent, violet_tracks, 0.0044, purple)
    traces("Barramentos entre camadas", parent, links, 0.0035, faint)

    def orb(name, radius, material):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius)
        obj = bpy.context.object
        obj.name = name
        obj.parent = parent
        obj.data.materials.append(material)
        return obj

    for tick, (start_ring, end_ring, theta) in enumerate((
        (1, 5, 0.4), (6, 3, 2.4), (3, 7, 4.2), (7, 4, 5.2),
        (2, 6, 1.45), (5, 2, 3.15), (4, 7, 5.67),
    )):
        start = 5 + tick * 16
        source_radius, target_radius = radii[start_ring], radii[end_ring]
        incoming = [polar(source_radius, theta + offset, 0.16) for offset in (-0.54, -0.27, 0)]
        jump = [polar(source_radius + (target_radius - source_radius) * i / 6,
                      theta + 0.35 * i / 6, 0.16 + 0.42 * sin(pi * i / 6)) for i in range(1, 7)]
        outgoing = [polar(target_radius, theta + offset, 0.16) for offset in (0.46, 0.64, 0.80)]
        path = [*incoming, *jump, *outgoing]
        for module, index in (("Coleta", 2), ("Transformação", 8)):
            position = path[index]
            corners = [position + Vector((x, y, 0)) for x, y in ((-.059,-.039),(.059,-.039),(.059,.039),(-.059,.039),(-.059,-.039))]
            traces(module + f" · módulo {tick + 1}", parent, [corners], 0.007, cyan if index == 2 else purple)
            flash = orb(module + f" · ativação {tick + 1}", 0.043, bright if index == 2 else altered)
            flash.location = position
            at = start + 1.45 * index
            for frame, scale in ((1, 0), (at - 2, 0), (at, 1.4), (at + 5, 0), (145, 0)):
                flash.scale = (scale,) * 3
                flash.keyframe_insert(data_path="scale", frame=frame)
        for tail, radius in ((0, 0.022), (2, 0.013), (4, 0.008)):
            # Violet copies take over after the target module receives the packet.
            for name, material, first, last in (("Coleta", bright, 0, 8), ("Dados reemitidos", altered, 8, 11)):
                spark = orb(f"{name} · pacote {tick + 1}", radius, material)
                spark.location = path[first]
                for frame in (1, 145):
                    spark.keyframe_insert(data_path="location", frame=frame)
                    spark.scale = (0,) * 3
                    spark.keyframe_insert(data_path="scale", frame=frame)
                for i in range(first, last + 1):
                    frame = start + 1.45 * i + tail
                    spark.location = path[i]
                    scale = 0 if i in (first, last) else 1
                    spark.scale = (scale,) * 3
                    spark.keyframe_insert(data_path="location", frame=frame)
                    spark.keyframe_insert(data_path="scale", frame=frame)
        traces("Salto em profundidade", parent, [[incoming[-1], *jump]], 0.003, faint)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.52)
    shell = bpy.context.object
    shell.name = "Esfera de vidro · interior translúcido"
    shell.parent = parent
    for face in shell.data.polygons:
        face.use_smooth = True
    glass = bpy.data.materials.new("Vidro frio · contorno Fresnel")
    glass.use_nodes = True
    glass.surface_render_method = "BLENDED"
    shell.data.materials.append(glass)
    tree = glass.node_tree
    tree.nodes.clear()
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    rim = tree.nodes.new("ShaderNodeEmission")
    rim.inputs["Color"].default_value = (0.09, 0.46, 0.95, 1)
    rim.inputs["Strength"].default_value = 1.25
    fresnel = tree.nodes.new("ShaderNodeFresnel")
    fresnel.inputs["IOR"].default_value = 1.16
    mix = tree.nodes.new("ShaderNodeMixShader")
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    for a, b in ((fresnel.outputs[0], mix.inputs[0]), (transparent.outputs[0], mix.inputs[1]),
                 (rim.outputs[0], mix.inputs[2]), (mix.outputs[0], output.inputs["Surface"])):
        tree.links.new(a, b)
    traces("Reflexos do vidro", parent,
           [segment(0.49, 0.56, 0.94, 0.23), segment(0.44, 3.42, 0.64, 0.30)],
           0.010, cyan, taper=True)
    inner = [segment(radius, phase, 0.92, -0.28)
             for radius in (0.16, 0.26, 0.37) for phase in (0.26, 2.29, 4.48)]
    traces("Circuitos visíveis através do vidro", parent, inner, 0.0045, faint)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
    for frame, scale in ((1, 0.83), (17, 0.70), (39, 1.20), (58, 0.96), (78, 0.72),
                         (102, 1.24), (123, 1.04), (145, 0.83)):
        parent.scale = (scale,) * 3
        parent.keyframe_insert(data_path="scale", frame=frame)


def relief_presence(scene, artwork):
    image = bpy.data.images.load(str(artwork.resolve()), check_existing=False)
    image.pack()
    width, height = image.size
    ratio = height / width
    center = (0.510, 0.499)
    camera = scene.camera
    camera.data.type = "PERSP"
    camera.data.lens = 55
    camera.data.sensor_width = 36
    distance = 9.7
    span = distance * 36 / 55 * 1.035
    pivot = rotor("Presence · volume animado", (0, 0, 0))
    steps = 108
    vertices, coordinates, faces = [], [], []

    def surface(u, v, lift=0):
        x, y = (u - 0.5) * 2, (v - 0.5) * 2
        rho = (x * x + y * y) ** 0.5
        depth = max(0, 1 - (rho / 0.97) ** 2) ** 1.2
        z = depth * (1.45 + 0.22 * sin(14 * rho) + 0.13 * sin(9 * x + 4 * y)) + lift
        scale = (distance - z) / distance
        return (x * span * scale / 2, y * span * ratio * scale / 2, z)

    for j in range(steps + 1):
        for i in range(steps + 1):
            u, v = i / steps, j / steps
            vertices.append(surface(u, v))
            coordinates.append((u, v))
    for j in range(steps):
        for i in range(steps):
            a = j * (steps + 1) + i
            faces.append((a, a + 1, a + steps + 2, a + steps + 1))
    mesh = bpy.data.meshes.new("Malha de profundidade da referência")
    mesh.from_pydata(vertices, [], faces)
    uv = mesh.uv_layers.new(name="Projeção da referência")
    for loop in mesh.loops:
        uv.data[loop.index].uv = coordinates[loop.vertex_index]
    plate = bpy.data.objects.new("Circuitos da referência · relevo 3D", mesh)
    scene.collection.objects.link(plate)
    plate.parent = pivot
    material = emission("Projeção dos circuitos", (1, 1, 1), 1)
    mesh.materials.append(material)
    tree = material.node_tree
    texture = tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    dist = tree.nodes.new("ShaderNodeVectorMath")
    dist.operation = "DISTANCE"
    dist.inputs[1].default_value = (*center, 0)
    coords = tree.nodes.new("ShaderNodeTexCoord")
    fade = tree.nodes.new("ShaderNodeMapRange")
    fade.inputs["From Min"].default_value = 0.076
    fade.inputs["From Max"].default_value = 0.091
    fade.interpolation_type = "SMOOTHERSTEP"
    mask = tree.nodes.new("ShaderNodeMixRGB")
    mask.inputs[1].default_value = (0.003, 0.008, 0.034, 1)
    emitter = next(n for n in tree.nodes if n.type == "EMISSION")
    for a, b in ((coords.outputs["UV"], texture.inputs["Vector"]), (coords.outputs["UV"], dist.inputs[0]),
                 (dist.outputs["Value"], fade.inputs["Value"]), (fade.outputs[0], mask.inputs[0]),
                 (texture.outputs["Color"], mask.inputs[2]), (mask.outputs[0], emitter.inputs["Color"])):
        tree.links.new(a, b)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.44,
                                        location=(0.058, -0.005, 1.92))
    ball = bpy.context.object
    ball.name = "Núcleo de vidro · esfera"
    ball.parent = pivot
    for polygon in ball.data.polygons:
        polygon.use_smooth = True
    glass = bpy.data.materials.new("Vidro · transparência e reflexo Fresnel")
    glass.use_nodes = True
    glass.surface_render_method = "BLENDED"
    ball.data.materials.append(glass)
    tree = glass.node_tree
    tree.nodes.clear()
    facing = tree.nodes.new("ShaderNodeFresnel")
    facing.inputs["IOR"].default_value = 1.13
    clear = tree.nodes.new("ShaderNodeBsdfTransparent")
    rim = tree.nodes.new("ShaderNodeEmission")
    rim.inputs["Color"].default_value = (0.1, 0.36, 1, 1)
    rim.inputs["Strength"].default_value = 1.55
    mix = tree.nodes.new("ShaderNodeMixShader")
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    for a, b in ((facing.outputs[0], mix.inputs[0]), (clear.outputs[0], mix.inputs[1]),
                 (rim.outputs[0], mix.inputs[2]), (mix.outputs[0], out.inputs["Surface"])):
        tree.links.new(a, b)
    cool = emission("Reflexo frio", (0.20, 0.68, 1), 1.6)
    highlight = [(0.058 + 0.34 * cos(0.53 + i * 0.074),
                  0.325 * sin(0.53 + i * 0.074), 2.21) for i in range(25)]
    traces("Reflexo curvo na esfera", pivot, [highlight], 0.015, cool, taper=True)

    violet = emission("Pacote processado", (0.38, 0.07, 1), 5)
    packet = emission("Pacote em trânsito", (0.08, 0.55, 1), 7)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    for index, (start, points) in enumerate((
        (9, ((.32,.75),(.39,.67),(.45,.67),(.54,.69),(.62,.72))),
        (33, ((.86,.55),(.77,.52),(.71,.49),(.65,.47),(.60,.46))),
        (58, ((.22,.39),(.28,.33),(.34,.28),(.41,.20),(.46,.19))),
        (81, ((.84,.32),(.77,.33),(.69,.37),(.66,.39),(.61,.40))),
        (107, ((.41,.85),(.47,.83),(.54,.80),(.58,.72),(.64,.64))),
    )):
        for lag, size in ((0, 0.026), (2, 0.015), (4, 0.010)):
            for material, begin, end in ((packet, 0, 2), (violet, 2, 4)):
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=size)
                spark = bpy.context.object
                spark.name = f"Transferência entre anéis · {index + 1}"
                spark.parent = pivot
                spark.data.materials.append(material)
                for frame in (1, 145):
                    spark.location = surface(*points[begin], 0.09)
                    spark.scale = (0,) * 3
                    spark.keyframe_insert(data_path="location", frame=frame)
                    spark.keyframe_insert(data_path="scale", frame=frame)
                for i in range(17):
                    t = i / 16
                    section = min(int(t * 2), 1)
                    w = t * 2 - section
                    a, b = points[begin + section], points[begin + section + 1]
                    u, v = (p + (q - p) * w for p, q in zip(a, b))
                    spark.location = surface(u, v, 0.09 + 0.38 * sin(pi * t))
                    spark.scale = (sin(pi * t) ** 0.3 if 0 < i < 16 else 0,) * 3
                    frame = start + lag + (10 if begin else 0) + 12 * t
                    spark.keyframe_insert(data_path="location", frame=frame)
                    spark.keyframe_insert(data_path="scale", frame=frame)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
    scene.view_settings.view_transform = "Standard"
    for frame, angle, scale in ((1, 0, 0.93), (36, 8, 1.04), (73, 0, 0.80),
                                (109, -8, 1.04), (145, 0, 0.93)):
        theta = radians(angle)
        camera.location = (distance * sin(theta), 0.27 * sin(theta * 4), distance * cos(theta))
        camera.rotation_euler = (Vector((0, 0, 0.50)) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        pivot.scale = (scale,) * 3
        pivot.keyframe_insert(data_path="scale", frame=frame)


def sphere_presence(scene, seed):
    from mathutils import Euler

    rng = Random(seed)
    assembly = rotor("ARTEMIS · esfera completa", (0, 0, 0))
    scene.view_settings.view_transform = "AgX"
    camera = scene.camera
    camera.data.lens = 54
    colors = [
        emission("Ciano ionizado", (0.025, 0.53, 1), 5),
        emission("Violeta ionizado", (0.35, 0.092, 1), 6),
        emission("Azul profundo", (0.015, 0.12, 0.65), 1.45),
        emission("Barramentos latentes", (0.04, 0.024, 0.20), 0.85),
    ]
    paths = [[] for _ in colors]
    layers = (0.66, 0.98, 1.28, 1.57, 1.90, 2.12, 2.31)

    def circular(radius, longitude, latitude, transform):
        return transform @ Vector((radius * cos(latitude) * cos(longitude),
                                   radius * cos(latitude) * sin(longitude), radius * sin(latitude)))

    circuits = []
    for shell_index, radius in enumerate(layers):
        for direction in range(3):
            matrix = Euler(tuple(radians(a) for a in (
                76 + direction * 49 + shell_index * 4,
                -12 + direction * 33 - shell_index * 4,
                8 + direction * 46 + shell_index * 3))).to_matrix()
            for band in range(5):
                latitude = (band - 2) * 0.24
                for lane in (0.0, 0.028, -0.016):
                    for k in range(10):
                        a = k * tau / 10 + band * 0.12 + shell_index * 0.20
                        sweep = rng.uniform(0.22, 0.55)
                        strip = [circular(radius + lane, a + sweep * i / 24, latitude, matrix)
                                 for i in range(25)]
                        highlight = lane == 0 and shell_index > 0 and (
                            (direction == 0 and band in (1, 3) and k % 3 != 0)
                            or (direction == 1 and band == 2 and k % 4 == 0)
                        )
                        channel = (band + k + shell_index) % 2 if highlight else rng.choice((2, 3))
                        paths[channel].append(strip)
                        if lane == 0 and k % 3 == 1:
                            paths[2].append([strip[-1], circular(radius + 0.043, a + sweep + 0.028, latitude + 0.085, matrix)])
                            if shell_index > 0:
                                circuits.append((strip, shell_index, (direction + shell_index) % 2))
                for pin in range(48):
                    if rng.random() < 0.60:
                        a = pin * tau / 48
                        paths[2 if pin % 7 == 0 else 3].append([
                            circular(radius + 0.028, a, latitude, matrix),
                            circular(radius + 0.030, a + 0.012, latitude + (0.072 if pin % 4 == 0 else 0.031), matrix),
                        ])
    for i, strands in enumerate(paths):
        traces(f"Camadas completas · circuito {i + 1}", assembly, strands,
               (0.0056, 0.0056, 0.003, 0.002)[i], colors[i])

    # Build the reference's curved plates and exposed bus rails as geometry.
    # Each patch follows a spherical surface and occupies a different depth.
    panel_vertices, panel_faces, panel_edges, panel_rails = [], [], [], []
    rng_panels = Random(seed + 73)
    surface_frame = Euler((radians(81), radians(-11), radians(18))).to_matrix()
    for index in range(19):
        longitude = tau * index / 19 + rng_panels.uniform(-0.09, 0.09)
        latitude = rng_panels.choice((-0.57, -0.33, 0.27, 0.54))
        radius = rng_panels.choice((1.86, 2.08, 2.29, 2.36))
        sweep = rng_panels.uniform(0.10, 0.24)
        breadth = rng_panels.uniform(0.12, 0.32)
        strips = []
        for row in range(2):
            strips.append([circular(radius, longitude + sweep * col / 12,
                                    latitude + row * breadth, surface_frame) for col in range(13)])
        offset = len(panel_vertices)
        panel_vertices.extend(point for strip in strips for point in strip)
        panel_faces.extend((offset + j, offset + j + 1, offset + j + 14, offset + j + 13)
                           for j in range(12))
        edges = [*strips, [strips[0][0], strips[1][0]], [strips[0][-1], strips[1][-1]]]
        panel_edges.extend(edges)
        panel_rails.extend([
            [circular(radius + .009, longitude + sweep * j / 12,
                      latitude + fraction * breadth, surface_frame) for j in range(13)]
            for fraction in (.21, .29, .67, .74, .81)
        ])
    mesh = bpy.data.meshes.new("Placas curvadas sobre a esfera")
    mesh.from_pydata(panel_vertices, [], panel_faces)
    panels = bpy.data.objects.new("Painéis de dados em vidro", mesh)
    bpy.context.collection.objects.link(panels)
    panels.parent = assembly
    panel_surface = bpy.data.materials.new("Vidro de circuito · azul profundo")
    panel_surface.use_nodes = True
    panel_surface.surface_render_method = "BLENDED"
    mesh.materials.append(panel_surface)
    tree = panel_surface.node_tree
    tree.nodes.clear()
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    face = tree.nodes.new("ShaderNodeEmission")
    face.inputs[0].default_value = (0.008, 0.066, 0.28, 1)
    face.inputs[1].default_value = 0.74
    mix = tree.nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = .18
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    for a, b in ((transparent.outputs[0], mix.inputs[1]), (face.outputs[0], mix.inputs[2]),
                 (mix.outputs[0], output.inputs[0])):
        tree.links.new(a, b)
    traces("Bordas dos painéis curvos", assembly, panel_edges, 0.0029, colors[2])
    traces("Trilhas internas dos painéis", assembly, panel_rails, 0.0018, colors[2])
    for index, radius, tilt in ((0, 1.14, (81, -16, 31)), (1, 1.64, (66, 20, -27)),
                                (0, 2.22, (102, -19, 21))):
        transform = Euler(tuple(radians(angle) for angle in tilt)).to_matrix()
        accents = [[circular(radius + offset, begin + jump * .011, 0, transform)
                    for jump in range(87)] for offset in (0, .014, .032) for begin in (0.13, 2.5, 4.68)]
        traces("Arcos principais segmentados", assembly, accents, 0.0065, colors[index], taper=True)

    for index, (trace, layer, channel) in enumerate(rng.sample(circuits, 14)):
        end = trace[-1]
        other_radius = layers[max(0, layer - 2)]
        destination = end.normalized() * other_radius
        tangent = end.normalized().cross(Vector((0, 0, 1))) * 0.22
        path = [*trace[12::4], *[end.lerp(destination, i / 10) + tangent * sin(pi * i / 10)
                                for i in range(1, 11)]]
        traces("Ponte entre camadas", assembly, [path[3:]], 0.0035, colors[2], taper=True)
        # The receiving module is a short bracket hugging its spherical layer.
        corner = destination.normalized().cross(Vector((0, 1, 0))).normalized() * 0.043
        up = destination.normalized().cross(corner).normalized() * 0.029
        traces("Nódulo de IA", assembly,
               [[destination - corner - up, destination - corner + up,
                 destination + corner + up, destination + corner - up]], 0.007, colors[1 - channel])
        start = 5 + index * 8
        for delay, radius in ((0, 0.030), (2, 0.016), (4, 0.010)):
            for phase, subpath in enumerate((path[:7], path[6:])):
                bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius)
                spark = bpy.context.object
                spark.name = "Coleta" if phase == 0 else "Dados transformados"
                spark.parent = assembly
                spark.data.materials.append(colors[(channel + phase) % 2])
                for frame in (1, 145):
                    spark.location = subpath[0]
                    spark.scale = (0,) * 3
                    spark.keyframe_insert(data_path="location", frame=frame)
                    spark.keyframe_insert(data_path="scale", frame=frame)
                for n, position in enumerate(subpath):
                    t = n / (len(subpath) - 1)
                    frame = start + delay + phase * 8 + 9 * t
                    spark.location = position
                    spark.scale = (sin(pi * t) ** 0.38 if 0 < n < len(subpath) - 1 else 0,) * 3
                    spark.keyframe_insert(data_path="location", frame=frame)
                    spark.keyframe_insert(data_path="scale", frame=frame)

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.53)
    core = bpy.context.object
    core.name = "Núcleo de vidro translúcido"
    core.parent = assembly
    for face in core.data.polygons:
        face.use_smooth = True
    glass = bpy.data.materials.new("Vidro com reflexos ciano e violeta")
    glass.use_nodes = True
    glass.surface_render_method = "BLENDED"
    core.data.materials.append(glass)
    tree = glass.node_tree
    tree.nodes.clear()
    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    transparent.inputs[0].default_value = (0.78, 0.87, 1, 1)
    facing = tree.nodes.new("ShaderNodeFresnel")
    facing.inputs["IOR"].default_value = 1.12
    shader = tree.nodes.new("ShaderNodeEmission")
    shader.inputs["Strength"].default_value = 0.68
    coordinates = tree.nodes.new("ShaderNodeTexCoord")
    axes = tree.nodes.new("ShaderNodeSeparateXYZ")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.19, 0.035, 0.66, 1)
    ramp.color_ramp.elements[1].color = (0.02, 0.57, 1, 1)
    mix = tree.nodes.new("ShaderNodeMixShader")
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    for a, b in ((coordinates.outputs["Generated"], axes.inputs[0]), (axes.outputs["Y"], ramp.inputs[0]),
                 (ramp.outputs[0], shader.inputs[0]), (facing.outputs[0], mix.inputs[0]),
                 (transparent.outputs[0], mix.inputs[1]), (shader.outputs[0], mix.inputs[2]),
                 (mix.outputs[0], output.inputs["Surface"])):
        tree.links.new(a, b)
    for i in range(7):
        matrix = Euler((i * .54, i * .62, i * .39)).to_matrix()
        tracks = [[circular(0.37 + i * 0.012, j * tau / 8 + k * .017, 0, matrix)
                   for k in range(22)] for j in range(8)]
        traces("Circuitos sob o vidro", assembly, tracks, 0.004, colors[i % 3], taper=True)

    bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
    for frame, yaw, pitch, size in ((1, -9, 9, .91), (38, 27, -12, 1.21),
                                    (76, 6, -4, .77), (110, -35, 17, 1.12), (145, -9, 9, .91)):
        camera.location = circular(10.5, radians(yaw), radians(pitch), Euler((pi / 2, 0, pi / 2)).to_matrix())
        camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
        assembly.scale = (size,) * 3
        for obj, prop in ((camera, "location"), (camera, "rotation_euler"), (assembly, "scale")):
            obj.keyframe_insert(data_path=prop, frame=frame)


def wrap_presence(scene, artwork):
    image = bpy.data.images.load(str(artwork.resolve()), check_existing=False)
    image.pack()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=144, ring_count=96, radius=2)
    globe = bpy.context.object
    globe.name = "ARTEMIS · esfera texturizada"
    # Orthographic UV projection on both hemispheres shares coordinates at
    # their equator and keeps the supplied front undistorted.
    globe.data.uv_layers.active.name = "Projeção frontal contínua"
    uv = globe.data.uv_layers.active.uv
    for loop in globe.data.loops:
        x, y, _ = globe.data.vertices[loop.vertex_index].co
        uv[loop.index].vector = (0.50 + 0.45 * x / 2, 0.51 + 0.469 * y / 2)
    for face in globe.data.polygons:
        face.use_smooth = True
    material = emission("Imagem original · emissão neutra", (1, 1, 1), 1)
    globe.data.materials.append(material)
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = image
    emitter = next(node for node in material.node_tree.nodes if node.type == "EMISSION")
    material.node_tree.links.new(texture.outputs["Color"], emitter.inputs["Color"])
    camera = scene.camera
    camera.location = (0, 0, 10)
    camera.rotation_euler = (0, 0, 0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 5.25
    scene.view_settings.view_transform = "Standard"
    for frame, angle in ((1, 0), (145, tau)):
        globe.rotation_euler = (0, angle, 0)
        globe.keyframe_insert(data_path="rotation_euler", frame=frame)
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
    for frame, scale in ((1, 1.03), (35, 1.19), (70, 0.84), (108, 1.17), (145, 1.03)):
        globe.scale = (scale,) * 3
        globe.keyframe_insert(data_path="scale", frame=frame)


def scene_setup(size, seed, artwork=None, circuits=False, relief=False, sphere=False, wrap=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    scene = bpy.context.scene
    scene.name = "ARTEMIS · Presence"
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 24
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.world = bpy.data.worlds.new("Preto")
    scene.world.color = (0, 0, 0)
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0, 0, 0, 1)
    background.inputs["Strength"].default_value = 0
    data = bpy.data.cameras.new("Lente")
    camera = bpy.data.objects.new("Câmera", data)
    scene.collection.objects.link(camera)
    camera.location = (0.25, -0.35, 10.6)
    camera.rotation_euler = (-Vector(camera.location)).to_track_quat("-Z", "Y").to_euler()
    data.lens = 66
    scene.camera = camera

    if wrap:
        wrap_presence(scene, artwork)
        return scene
    if sphere:
        sphere_presence(scene, seed)
    elif relief:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
        relief_presence(scene, artwork)
    elif circuits:
        circuit_presence(scene, seed)
    elif artwork:
        artwork_presence(scene, artwork)
    else:
        rng = Random(seed)
        materials = {name: emission(name, *values) for name, values in PALETTE.items()}
        wisps(rng, materials)
        mist()
        impulses(rng, materials)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.055)
        core = bpy.context.object
        core.name = "Núcleo pulsante"
        core.data.materials.append(materials["Branco gelo"])
        for frame, scale in ((1, 1), (37, 1.32), (73, 1), (109, 1.24), (145, 1)):
            core.scale = (scale,) * 3
            core.keyframe_insert(data_path="scale", frame=frame)

    tree = bpy.data.node_groups.new("Brilho da Presence", "CompositorNodeTree")
    scene.compositing_node_group = tree
    tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Fog Glow"
    glare.inputs["Threshold"].default_value = 1.05 if artwork else 0.25 if circuits else 0.4
    glare.inputs["Strength"].default_value = 1.1 if artwork else 2.2
    glare.inputs["Size"].default_value = 0.65
    output = tree.nodes.new("NodeGroupOutput")
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], output.inputs["Image"])
    return scene


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, choices=(360, 540, 720), default=540)
    parser.add_argument("--mode", choices=("still", "loop"), default="still")
    parser.add_argument("--seed", type=int, default=2420)
    parser.add_argument("--artwork", type=Path)
    parser.add_argument("--circuits", action="store_true")
    parser.add_argument("--relief", action="store_true")
    parser.add_argument("--sphere", action="store_true")
    parser.add_argument("--wrap", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene = scene_setup(args.size, args.seed, args.artwork, args.circuits, args.relief, args.sphere, args.wrap)
    scene.frame_set(1 if args.relief or args.wrap else 37)
    scene.render.filepath = str(output / "presence.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "artemis-presence.blend"))
    bpy.ops.render.render(write_still=True)
    if args.mode == "loop":
        frames = output / "frames"
        frames.mkdir(exist_ok=True)
        scene.render.filepath = str(frames / "presence-")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
