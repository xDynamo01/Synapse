"""Static, independently editable hologram study. No image maps or animation."""
import bpy
import math
import json
from pathlib import Path
from mathutils import Vector, Euler

OUT = Path(__file__).resolve().parents[2] / 'target/presence-blender/layered-model-v1'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.resolution_x = scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.world = bpy.data.worlds.new('Espaço escuro')
scene.world.use_nodes = True
scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.002, .004, .012, 1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value = .18
scene.view_settings.view_transform = 'AgX'

def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c

core = collection('01 · Núcleo de vidro')
inner = collection('02 · Anéis internos')
outer = collection('03 · Arcos externos')
panels = collection('04 · Painéis e conexões')
studio = collection('05 · Câmeras e iluminação')

def move(obj, c):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    c.objects.link(obj)

def material(name, color, strength=0, glass=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes
    n.clear()
    out = n.new('ShaderNodeOutputMaterial')
    if glass:
        s = n.new('ShaderNodeBsdfPrincipled')
        s.inputs['Base Color'].default_value = (*color, 1)
        s.inputs['Roughness'].default_value = .1
        s.inputs['Transmission Weight'].default_value = 1
        s.inputs['IOR'].default_value = 1.16
        s.inputs['Coat Weight'].default_value = .3
    else:
        s = n.new('ShaderNodeEmission')
        s.inputs[0].default_value = (*color, 1)
        s.inputs[1].default_value = strength
    m.node_tree.links.new(s.outputs[0], out.inputs[0])
    return m

cyan = material('Ciano · borda de luz', (.015, .5, 1), 3)
violet = material('Violeta · acentos', (.38, .035, 1), 2.5)
dim = material('Azul · circuitos discretos', (.025, .12, .38), .8)
white = material('Conexão · branco ciano', (.35, .85, 1), 5)
glass = material('Vidro óptico azul', (.75, .92, 1), glass=True)

def line(name, points, mat, width, c):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = width
    curve.bevel_resolution = 2
    sp = curve.splines.new('POLY')
    sp.points.add(len(points)-1)
    for p, co in zip(sp.points, points):
        p.co = (*co, 1)
    obj = bpy.data.objects.new(name, curve)
    c.objects.link(obj)
    obj.data.materials.append(mat)
    return obj

def point(r, a, lat, matrix):
    return matrix @ Vector((r*math.cos(lat)*math.cos(a), r*math.cos(lat)*math.sin(a), r*math.sin(lat)))

def arc(name, r, start, end, tilt, mat, width, c, lat=0):
    matrix = Euler(tilt).to_matrix()
    return line(name, [point(r, math.radians(start+(end-start)*i/100), lat, matrix) for i in range(101)], mat, width, c)

def sphere(name, radius, mat, c, location=(0,0,0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=radius, location=location)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    move(ob, c)
    return ob

sphere('Núcleo · casca transparente', .46, glass, core)
for i in range(3):
    arc('Núcleo · filamento suspenso', .31+i*.035, 25+i*65, 210+i*45,
        (.5+i*.55, .3+i*.7, .4), cyan if i != 1 else violet, .003, core)

# Three orbital structures, each with its own tilted plane and ample gaps.
for index, (r, tilt, segments) in enumerate([
    (.78, (.35,.45,.1), [(5,155),(195,310)]),
    (1.28, (1.0,-.38,.25), [(10,130),(165,278),(310,348)]),
    (1.85, (.28,.22,.12), [(4,68),(87,170),(194,263),(286,342)]),
    (2.02, (1.18,.75,-.4), [(12,122),(165,235),(280,326)]),
]):
    c = inner if index < 2 else outer
    for j,(a,b) in enumerate(segments):
        arc('Arco principal %d.%d'%(index,j), r, a,b,tilt,cyan if j%3 else violet,.007 if index==2 else .004,c)
        arc('Trilho paralelo %d.%d'%(index,j), r-.035,a+2,b-4,tilt,dim,.0018,c)
    # Short marks confined to small sectors rather than an all-over wire mesh.
    matrix = Euler(tilt).to_matrix()
    for k in range(20):
        a = math.radians(93+k*2.4)
        line('Escala orbital', [point(r-.065,a,0,matrix),point(r-.045,a,0,matrix)], dim,.0017,c)

# Separate curved glass panels on a genuine spherical surface.
matrix = Euler((.25,.2,.1)).to_matrix()
for idx,(a0,a1,l0,l1) in enumerate([
    (25,48,-.32,.48),(57,76,.10,.64),(101,124,-.38,.14),
    (143,163,-.18,.45),(205,225,-.58,.04),(253,274,-.28,.36),
    (302,320,-.12,.52),(340,353,-.45,.04),
]):
    a0,a1 = map(math.radians,(a0,a1))
    verts = [point(1.92,a0+(a1-a0)*u/12,l0+(l1-l0)*v/10,matrix) for u in range(13) for v in range(11)]
    faces = [(u*11+v,(u+1)*11+v,(u+1)*11+v+1,u*11+v+1) for u in range(12) for v in range(10)]
    mesh = bpy.data.meshes.new('Painel curvo')
    mesh.from_pydata(verts,[],faces)
    obj = bpy.data.objects.new('Lâmina de vidro %02d'%idx,mesh)
    panels.objects.link(obj)
    mesh.materials.append(glass)
    solid = obj.modifiers.new('Espessura óptica','SOLIDIFY')
    solid.thickness = .006
    for p in mesh.polygons:
        p.use_smooth = True
    for edge in (l0,l1):
        line('Contorno do painel',[point(1.925,a0+(a1-a0)*u/50,edge,matrix) for u in range(51)],dim,.002,panels)
    for k in range(4):
        lat = l0+(l1-l0)*(k+1)/5
        line('Circuito gravado',[point(1.93,a0+(a1-a0)*u/45,lat,matrix) for u in range(36)],cyan if k==1 else dim,.0018,panels)
    # Only one small endpoint per panel; no particle cloud.
    sphere('Terminal fixo',.012,white,panels,point(1.935,a0+(a1-a0)*.78,l0+(l1-l0)*.4,matrix))

for i,(loc,col,power,size) in enumerate([((2,-3,4),(.12,.6,1),500,3),((-3,1,2),(.55,.12,1),650,2),((0,3,-2),(.1,.4,1),350,2)]):
    data=bpy.data.lights.new('Reflexo suave','AREA'); data.energy=power; data.color=col; data.shape='DISK'; data.size=size
    ob=bpy.data.objects.new('Iluminação %d'%i,data); studio.objects.link(ob); ob.location=loc
    ob.rotation_euler=(-ob.location).to_track_quat('-Z','Y').to_euler()

data=bpy.data.cameras.new('Perspectiva'); camera=bpy.data.objects.new('Câmera',data);studio.objects.link(camera)
scene.camera=camera;data.lens=55
def aim(location):
    camera.location=location
    camera.rotation_euler=(-camera.location).to_track_quat('-Z','Y').to_euler()
aim((.7,-2.6,8.5))
tree=bpy.data.node_groups.new('Brilho controlado','CompositorNodeTree');scene.compositing_node_group=tree
tree.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
rl=tree.nodes.new('CompositorNodeRLayers');gl=tree.nodes.new('CompositorNodeGlare');out=tree.nodes.new('NodeGroupOutput')
gl.inputs['Type'].default_value='Fog Glow';gl.inputs['Threshold'].default_value=1.4;gl.inputs['Strength'].default_value=.65;gl.inputs['Size'].default_value=.45
tree.links.new(rl.outputs['Image'],gl.inputs['Image']);tree.links.new(gl.outputs['Image'],out.inputs[0])
assert not bpy.data.actions
assert not any(n.type=='TEX_IMAGE' for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes)
(OUT/'validation.json').write_text(json.dumps({'objects':len(bpy.data.objects),'layers':[c.name for c in (core,inner,outer,panels)],'animations':len(bpy.data.actions),'image_textures':0},indent=2),encoding='utf8')
scene.render.filepath=str(OUT/'model-front.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'synapse-layered-model.blend'))
bpy.ops.render.render(write_still=True)
aim((5,-3,6.5))
scene.render.filepath=str(OUT/'model-angle.png')
bpy.ops.render.render(write_still=True)
