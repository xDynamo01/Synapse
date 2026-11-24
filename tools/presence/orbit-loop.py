"""Build a seamless orbital animation from the approved static study."""
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[2] / 'target/presence-blender'
output = root / 'orbit-loop-v1'
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(root / 'bands-study-v11/synapse-core-bands.blend'))
scene = bpy.context.scene
scene.name = 'Idle'
scene.render.fps = 24
scene.render.fps_base = 1
scene.frame_start, scene.frame_end = 1, 480
closing_frame = scene.frame_end + 1
styles = ('Energia', 'Dados', 'Circuitos', 'Grade externa')
tilts, rotors = [], []

for index, style in enumerate(styles):
    tilt = bpy.data.objects[f'Eixo independente {index+1}']
    rotor = bpy.data.objects.new(f'Rotação · {style}', None)
    tilt.users_collection[0].objects.link(rotor)
    rotor.parent = tilt
    for piece in list(tilt.children):
        if piece != rotor:
            piece.parent = rotor
    particles = bpy.data.objects[f'{style} · partículas']
    particles.parent = rotor
    particles.matrix_parent_inverse = tilt.matrix_world.inverted()
    direction = 1 if index % 2 == 0 else -1
    # A linear driver has constant angular speed and repeats every 480 frames.
    rotor.driver_add('rotation_euler', 2).driver.expression = f'{direction * math.tau!r} * (frame - 1) / {scene.frame_end}'
    tilts.append(tilt)
    rotors.append(rotor)

for a, tilt in enumerate(tilts):
    normal = tilt.matrix_world.to_3x3() @ Vector((0,0,1))
    for other in tilts[:a]:
        assert abs(normal.dot(other.matrix_world.to_3x3() @ Vector((0,0,1)))) < .999

def poses(frame):
    scene.frame_set(frame)
    return [obj.matrix_world.copy() for obj in rotors]

start, middle, end = poses(1), poses(121), poses(closing_frame)
for first, quarter, last in zip(start,middle,end):
    assert max(abs(first[i][j]-last[i][j]) for i in range(4) for j in range(4)) < 1e-5
    assert max(abs(first[i][j]-quarter[i][j]) for i in range(4) for j in range(4)) > .1

scene.frame_set(1)
scene.render.filepath = str(output / 'frames' / 'orbit-')
bpy.ops.wm.save_as_mainfile(filepath=str(output / 'synapse-orbit-loop.blend'))

if '--preview' in sys.argv[sys.argv.index('--')+1:]:
    scene.render.resolution_x = scene.render.resolution_y = 480
    scene.cycles.samples = 4
    scene.frame_step = 3
    bpy.ops.render.render(animation=True)
