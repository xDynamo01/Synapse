"""Isolated static 3D core study, based on the user's violet/cyan reference."""
import bpy
import math
import random
import json
from pathlib import Path
from mathutils import Vector, Euler

OUT = Path(__file__).resolve().parents[2] / 'target/presence-blender/core-study-v2'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.resolution_x = scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.world = bpy.data.worlds.new('Fundo azul quase preto')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.001,.002,.009,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value = .15
scene.view_settings.view_transform = 'AgX'
rng = random.Random(2422)

def layer(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c

shell = layer('01 · Membrana translúcida')
energy = layer('02 · Luz central e filamentos')
studio = layer('04 · Câmera')

def emission(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True
    n = m.node_tree.nodes; n.clear()
    s = n.new('ShaderNodeEmission'); s.inputs[0].default_value = (*color,1); s.inputs[1].default_value = strength
    o = n.new('ShaderNodeOutputMaterial'); m.node_tree.links.new(s.outputs[0],o.inputs[0])
    return m

cyan = emission('Ciano elétrico',(.015,.55,1),5)
blue = emission('Circuito azul',(.025,.12,.8),1.5)
violet = emission('Filamento violeta',(.37,.018,1),2.8)
pink = emission('Plasma branco rosado',(.85,.22,1),18)
white = emission('Centro luminoso',(1,.65,.95),35)

def trace(name, points, mat, radius, collection):
    curve = bpy.data.curves.new(name,'CURVE'); curve.dimensions='3D'; curve.bevel_depth=radius; curve.bevel_resolution=2
    sp=curve.splines.new('POLY'); sp.points.add(len(points)-1)
    for p,co in zip(sp.points,points): p.co=(*co,1)
    ob=bpy.data.objects.new(name,curve); collection.objects.link(ob); curve.materials.append(mat)
    return ob

def ball(name, radius, mat, collection, location=(0,0,0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96,ring_count=48,radius=radius,location=location)
    ob=bpy.context.object; ob.name=name
    for c in list(ob.users_collection): c.objects.unlink(ob)
    collection.objects.link(ob); ob.data.materials.append(mat)
    for p in ob.data.polygons: p.use_smooth=True
    return ob

# Fresnel-weighted optical membrane: transparent front, luminous curved rim.
m=bpy.data.materials.new('Vidro holográfico · borda Fresnel');m.use_nodes=True
n=m.node_tree.nodes;n.clear();links=m.node_tree.links
transparent=n.new('ShaderNodeBsdfTransparent')
glass=n.new('ShaderNodeBsdfGlass');glass.inputs['Color'].default_value=(.65,.75,1,1);glass.inputs['Roughness'].default_value=.12;glass.inputs['IOR'].default_value=1.08
optical=n.new('ShaderNodeMixShader');optical.inputs[0].default_value=.12
links.new(transparent.outputs[0],optical.inputs[1]);links.new(glass.outputs[0],optical.inputs[2])
rim=n.new('ShaderNodeEmission');rim.inputs[0].default_value=(.08,.12,.9,1);rim.inputs[1].default_value=.55
f=n.new('ShaderNodeLayerWeight');f.inputs['Blend'].default_value=.3
power=n.new('ShaderNodeMath');power.operation='POWER';power.inputs[1].default_value=3
links.new(f.outputs['Facing'],power.inputs[0])
mix=n.new('ShaderNodeMixShader');links.new(power.outputs[0],mix.inputs[0]);links.new(optical.outputs[0],mix.inputs[1]);links.new(rim.outputs[0],mix.inputs[2])
out=n.new('ShaderNodeOutputMaterial');links.new(mix.outputs[0],out.inputs[0])
ball('Esfera transparente',1,m,shell)
ball('Ponto central branco',.045,white,energy)
ball('Halo compacto violeta',.035,pink,energy)

# Finite branching electrical filaments, embedded in volume rather than dots.
for i in range(13):
    az=2*math.pi*i/13+rng.uniform(-.2,.2)
    direction=Vector((math.cos(az),math.sin(az),rng.uniform(-.8,.8))).normalized()
    tangent=direction.cross(Vector((0,0,1))).normalized()
    path=[]
    bend=rng.uniform(-.38,.38)
    for j in range(29):
        t=j/28
        p=direction*(.06+.88*t)+tangent*(math.sin(j*1.8+i)*.018+math.sin(j*.62)*.025+bend*math.sin(t*3))*t
        p.z+=math.sin(j*.9+i)*.025*t
        path.append(p)
    trace('Descarga interna %02d'%i,path,pink if i%7==0 else violet,.0018 if i%7 else .0025,energy)
    if i%2==0:
        origin=path[17]
        branch=[origin.lerp((direction+tangent*.32).normalized()*.97,j/12)+tangent*math.sin(j*2)*.012 for j in range(13)]
        trace('Ramificação curta',branch,violet,.0012,energy)

# Sparse fractured seams across the translucent spherical skin.
for i in range(19):
    rot=Euler((rng.uniform(0,3),rng.uniform(0,3),rng.uniform(0,3))).to_matrix()
    start=rng.uniform(0,6)
    points=[]
    for j in range(48):
        a=start+j*.016;lat=.025*math.sin(j*1.7)+.018*math.cos(j*.5)
        points.append(rot@Vector((math.cos(a)*math.cos(lat),math.sin(a)*math.cos(lat),math.sin(lat))))
    trace('Fissura luminosa',points,violet if i%3 else blue,.0015,energy)

camera_data=bpy.data.cameras.new('Perspectiva');camera=bpy.data.objects.new('Câmera',camera_data);studio.objects.link(camera)
scene.camera=camera;camera_data.lens=58
def aim(p):
    camera.location=p;camera.rotation_euler=(-camera.location).to_track_quat('-Z','Y').to_euler()
aim((.1,-.15,5.7))
tree=bpy.data.node_groups.new('Halo do núcleo','CompositorNodeTree');scene.compositing_node_group=tree
tree.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
rl=tree.nodes.new('CompositorNodeRLayers');gl=tree.nodes.new('CompositorNodeGlare');o=tree.nodes.new('NodeGroupOutput')
gl.inputs['Type'].default_value='Fog Glow';gl.inputs['Threshold'].default_value=1;gl.inputs['Strength'].default_value=3.5;gl.inputs['Size'].default_value=.85
tree.links.new(rl.outputs['Image'],gl.inputs['Image']);tree.links.new(gl.outputs['Image'],o.inputs[0])
assert len(bpy.data.actions)==0
assert not any(node.type=='TEX_IMAGE' for mat in bpy.data.materials if mat.use_nodes for node in mat.node_tree.nodes)
(OUT/'validation.json').write_text(json.dumps({'animations':0,'image_textures':0,'objects':len(bpy.data.objects),'seed':2422},indent=2))
scene.render.filepath=str(OUT/'core-front.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'synapse-core.blend'))
bpy.ops.render.render(write_still=True)
aim((3,-1.3,4.8));scene.render.filepath=str(OUT/'core-angle.png');bpy.ops.render.render(write_still=True)
