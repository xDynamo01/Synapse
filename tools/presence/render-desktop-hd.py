"""Render native HD frames from the existing Presence scenes."""
import argparse
from pathlib import Path
import sys

import bpy

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=('idle', 'thinking', 'listening'))
parser.add_argument('--sample', type=int)
parser.add_argument('--eevee', action='store_true')
parser.add_argument('--end', type=int)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
root = Path(__file__).resolve().parents[2] / 'target/presence-blender'
sources = {
    'idle': 'orbit-loop-v1/synapse-idle.blend',
    'thinking': 'thinking-loop-v2/synapse-thinking.blend',
    'listening': 'listening-loop-v1/synapse-listening.blend',
}
bpy.ops.wm.open_mainfile(filepath=str(root / sources[args.mode]))
scene = bpy.context.scene
scene.render.resolution_x = scene.render.resolution_y = 800
scene.render.image_settings.color_mode = 'RGB'
scene.cycles.samples = 16
scene.cycles.use_denoising = True
scene.render.use_persistent_data = True
preferences = bpy.context.preferences.addons['cycles'].preferences
try:
    preferences.compute_device_type = 'HIP'
    gpu_devices = [device for device in preferences.get_devices_for_type('HIP') if device.type == 'HIP']
except (RuntimeError, TypeError):
    gpu_devices = []
if args.eevee:
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 12
    for material in bpy.data.materials:
        if material.node_tree and any(node.type == 'BSDF_TRANSPARENT' for node in material.node_tree.nodes):
            material.surface_render_method = 'BLENDED'
elif gpu_devices:
    for device in preferences.devices:
        device.use = device in gpu_devices
    scene.cycles.device = 'GPU'
    print('Render HIP:', ', '.join(device.name for device in gpu_devices), flush=True)
else:
    scene.cycles.device = 'CPU'
    print('Render CPU', flush=True)

output = root / 'desktop-hd' / args.mode
output.mkdir(parents=True, exist_ok=True)
if args.sample is not None:
    scene.frame_set(args.sample)
    scene.render.filepath = str(output / 'sample.png')
    bpy.ops.render.render(write_still=True)
else:
    scene.frame_step = 1
    if args.end:
        scene.frame_end = args.end
    scene.render.filepath = str(output / 'frame-')
    bpy.ops.render.render(animation=True)
