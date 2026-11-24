"""Build the Thinking loop and label its source animation Idle."""
from pathlib import Path
from random import Random
from math import sin, pi
import sys

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[2] / 'target/presence-blender'
idle = root / 'orbit-loop-v1'
output = root / 'thinking-loop-v2'
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(idle / 'synapse-orbit-loop.blend'))
scene = bpy.context.scene
scene.name = 'Idle'
bpy.ops.wm.save_as_mainfile(filepath=str(idle / 'synapse-idle.blend'))
scene.name = 'Pensando'
closing_frame = scene.frame_end + 1
assembly = bpy.data.objects.new('Retração do holograma', None)
scene.collection.objects.link(assembly)
for obj in list(scene.objects):
    if obj != assembly and obj.parent is None and obj.type not in {'CAMERA', 'LIGHT'}:
        obj.parent = assembly

for frame, scale in ((1,1), (52,.92), (124,.90), (196,.93), (262,.89),
                     (340,.92), (400,.94), (closing_frame,1)):
    assembly.scale = (scale,)*3
    assembly.keyframe_insert(data_path='scale', frame=frame)
scene.frame_set(1)

connections = bpy.data.collections.new('Pensando · transferências entre faixas')
scene.collection.children.link(connections)
rotors = [bpy.data.objects[f'Rotação · {style}'] for style in ('Energia','Dados','Circuitos','Grade externa')]
rng = Random(302)

def emitter(name, color):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    glow = tree.nodes.new('ShaderNodeEmission')
    glow.inputs[0].default_value = (*color,1)
    glow.inputs[1].default_value = 7
    tree.links.new(glow.outputs[0],tree.nodes.new('ShaderNodeOutputMaterial').inputs[0])
    return material

colors = (emitter('Transferência ciano',(.08,.58,1)), emitter('Transferência violeta',(.48,.10,1)))

def anchor(index):
    rotor = rotors[index]
    pieces = [obj for obj in rotor.children if obj.type == 'CURVE'
              and obj.name.startswith(('Fluxo de energia','Bloco de dados','Circuito gravado','Travessa aberta'))]
    piece = rng.choice(pieces)
    points = piece.data.splines[0].points
    obj = bpy.data.objects.new('Contato · '+rotor.name, None)
    connections.objects.link(obj)
    obj.parent = rotor
    obj.location = rotor.matrix_world.inverted() @ piece.matrix_world @ points[len(points)//2].co.to_3d()
    return obj

def transfer(source, target, frame, color):
    origin, destination = anchor(source), anchor(target)
    curve = bpy.data.curves.new('Pulso elétrico', 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = .004
    curve.bevel_resolution = 2
    spline = curve.splines.new('POLY')
    spline.points.add(24)
    amplitude = rng.uniform(.13, .27)
    direction = rng.choice((-1, 1))
    bends = rng.choice((1, 2, 3))
    phase = rng.uniform(-.8, .8)
    depth = rng.uniform(-.16, .16)
    for i, point in enumerate(spline.points):
        t = i / 24
        envelope = sin(pi * t)
        # Large irregular bends set the silhouette. Small alternating kinks
        # give the light a jagged edge without moving either contact point.
        bow = direction * amplitude * sin(bends * pi * t + phase)
        kink = (-1)**i * rng.uniform(.022,.065)
        point.co = (envelope * (bow + kink), t,
                    envelope * (depth * sin(2*pi*t+phase) + rng.uniform(-.04,.04)), 1)
    ray = bpy.data.objects.new('Transferência %d → %d'%(source+1,target+1),curve)
    connections.objects.link(ray)
    curve.materials.append(color)
    locate = ray.constraints.new('COPY_LOCATION')
    locate.target = origin
    track = ray.constraints.new('DAMPED_TRACK')
    track.target = destination
    track.track_axis = 'TRACK_Y'
    driver = ray.driver_add('scale',1).driver
    distance = driver.variables.new()
    distance.name = 'distance'
    distance.type = 'LOC_DIFF'
    distance.targets[0].id = origin
    distance.targets[1].id = destination
    driver.expression = 'distance'
    for offset, tail, head in ((-1,0,0),(0,0,0),(9,0,1),(12,.35,1),(20,1,1)):
        curve.bevel_factor_start = tail
        curve.bevel_factor_end = head
        for prop in ('bevel_factor_start','bevel_factor_end'):
            curve.keyframe_insert(data_path=prop,frame=frame+offset)
    return ray, origin, destination, frame

transfers = [transfer(a,b,frame,colors[i%2]) for i,(a,b,frame) in enumerate((
    (0,1,44),(1,2,59),(2,3,75),(3,2,127),(2,1,143),(1,0,159),
    (0,1,225),(1,2,239),(2,3,253),(3,2,304),(2,1,320),(1,0,336),
    (0,1,383),(1,2,399),(2,3,415),
))]

for ray, origin, destination, frame in transfers:
    scene.frame_set(frame+9)
    assert (ray.matrix_world.translation-origin.matrix_world.translation).length < .001
    assert (ray.matrix_world @ Vector((0,1,0))-destination.matrix_world.translation).length < .001
for frame in (1,closing_frame):
    scene.frame_set(frame)
    assert abs(assembly.scale.x-1) < .0001
    assert all(abs(ray.data.bevel_factor_end-ray.data.bevel_factor_start) < .0001 for ray,*_ in transfers)

scene.frame_set(1)
scene.render.filepath = str(output / 'frames' / 'thinking-')
bpy.ops.wm.save_as_mainfile(filepath=str(output / 'synapse-thinking.blend'))
if '--preview' in sys.argv[sys.argv.index('--')+1:]:
    scene.render.resolution_x = scene.render.resolution_y = 480
    scene.cycles.samples = 4
    scene.frame_step = 3
    bpy.ops.render.render(animation=True)
