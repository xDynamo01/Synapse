"""Apply a WAV speech envelope to a copy of the Idle hologram."""
from array import array
from math import ceil, sqrt
from pathlib import Path
import sys
import wave

import bpy

root = Path(__file__).resolve().parents[2] / 'target/presence-blender'
output = root / 'speaking-v1'
args = sys.argv[sys.argv.index('--') + 1:]
audio = Path(args[0]).resolve()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(root / 'orbit-loop-v1/synapse-idle.blend'))
scene = bpy.context.scene
scene.name = 'Falando'
fps = scene.render.fps

with wave.open(str(audio), 'rb') as wav:
    if wav.getsampwidth() != 2:
        raise ValueError('Use um WAV PCM de 16 bits.')
    channels, rate = wav.getnchannels(), wav.getframerate()
    samples = array('h', wav.readframes(wav.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()

levels = []
for i in range(ceil(len(samples) / channels / rate * fps)):
    start = int(i * rate / fps) * channels
    stop = int((i + 1) * rate / fps) * channels
    window = samples[start:stop]
    levels.append(sqrt(sum(value * value for value in window) / len(window)) if window else 0)
reference = sorted(levels)[int(len(levels)*.90)] if levels else 0
reference = reference or max(levels, default=0)
if not reference:
    raise ValueError('O WAV não contém fala audível.')

envelope = [0.0]
for level in levels + [0]*15:
    target = min(1, max(0, (level/reference-.035)/.965))
    weight = .64 if target > envelope[-1] else .28
    envelope.append(envelope[-1] + (target-envelope[-1])*weight)
envelope.extend([0]*5)

assembly = bpy.data.objects.new('Expansão durante a fala', None)
scene.collection.objects.link(assembly)
for obj in list(scene.objects):
    if obj != assembly and obj.parent is None and obj.type not in {'CAMERA','LIGHT'}:
        obj.parent = assembly

rotors = [bpy.data.objects[f'Rotação · {name}'] for name in ('Energia','Dados','Circuitos','Grade externa')]
activity = 0.0
for i, level in enumerate(envelope):
    # Slower overall expansion, faster waves that travel outward from band to band.
    target = min(1, level*3)
    activity += (target-activity)*(.24 if target > activity else .10)
    size = 1 + .12*activity + .025*level
    if i == len(envelope)-1:
        size = 1
    assembly.scale = (size,)*3
    assembly.keyframe_insert(data_path='scale',frame=i+1)
    for index, rotor in enumerate(rotors):
        pulse = envelope[max(0,i-index*2)]
        rotor.scale = (1+.075*pulse, 1+.075*pulse, 1+.025*pulse)
        rotor.keyframe_insert(data_path='scale',frame=i+1)

scene.frame_end = len(envelope)
scene.frame_set(envelope.index(max(envelope))+1)
assert assembly.scale.x > 1.05
assert rotors[0].scale.x > 1.05
for frame in (1,scene.frame_end):
    scene.frame_set(frame)
    assert abs(assembly.scale.x-1) < 1e-5

sound = bpy.data.sounds.load(str(audio))
speaker = bpy.data.speakers.new('Voz de demonstração')
speaker.sound = sound
voice = bpy.data.objects.new('TTS · demonstração',speaker)
scene.collection.objects.link(voice)
bpy.ops.file.pack_all()
scene.frame_set(1)
scene.render.filepath = str(output / 'frames' / 'speaking-')
bpy.ops.wm.save_as_mainfile(filepath=str(output / 'synapse-speaking.blend'))
if '--preview' in args:
    scene.render.resolution_x = scene.render.resolution_y = 480
    scene.cycles.samples = 4
    scene.frame_step = 2
    bpy.ops.render.render(animation=True)
