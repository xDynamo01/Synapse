"""Create the listening animation with the Thinking loop's motion."""
from pathlib import Path
import sys

import bpy

root = Path(__file__).resolve().parents[2] / 'target/presence-blender'
output = root / 'listening-loop-v1'
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(root / 'thinking-loop-v2/synapse-thinking.blend'))
scene = bpy.context.scene
scene.name = 'Ouvindo'

transfers = bpy.data.collections['Pensando · transferências entre faixas']
transfer_names = [obj.name for obj in transfers.objects]
for obj in list(transfers.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
bpy.data.collections.remove(transfers)
assert all(scene.objects.get(name) is None for name in transfer_names)

assembly = bpy.data.objects['Retração do holograma']
for frame, expected in ((1, 1), (52, .92), (262, .89), (scene.frame_end + 1, 1)):
    scene.frame_set(frame)
    assert all(abs(value - expected) < 1e-5 for value in assembly.scale)

scene.frame_set(scene.frame_start)
scene.render.filepath = str(output / 'frames' / 'listening-')
bpy.ops.wm.save_as_mainfile(filepath=str(output / 'synapse-listening.blend'))

if '--preview' in sys.argv:
    scene.render.resolution_x = scene.render.resolution_y = 360
    scene.cycles.samples = 3
    scene.frame_step = 3
    bpy.ops.render.render(animation=True)
