"""Four editable holographic plate bands around the approved static core."""
import bpy
import math
import json
from random import Random
from pathlib import Path
from mathutils import Vector, Euler

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'target/presence-blender/core-study-v2/synapse-core.blend'
OUT = ROOT / 'target/presence-blender/bands-study-v11'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
original = set(bpy.data.objects.keys())
# This revision deliberately reduces the previously isolated core as requested.
CORE_SCALE = .58
for collection_name in ('01 · Membrana translúcida', '02 · Luz central e filamentos'):
    for obj in bpy.data.collections[collection_name].objects:
        obj.scale *= CORE_SCALE
        obj.location *= CORE_SCALE
core_membrane=bpy.data.materials['Vidro holográfico · borda Fresnel']
for node in core_membrane.node_tree.nodes:
    if node.type=='EMISSION':
        node.inputs['Strength'].default_value=.065
plasma = bpy.data.materials['Plasma branco rosado']
next(node for node in plasma.node_tree.nodes if node.type == 'EMISSION').inputs['Strength'].default_value = 7
scene.render.resolution_x = scene.render.resolution_y = 1200
scene.cycles.samples = 48

def emit(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True
    n=m.node_tree.nodes;n.clear()
    e=n.new('ShaderNodeEmission');e.inputs[0].default_value=(*color,1);e.inputs[1].default_value=strength
    o=n.new('ShaderNodeOutputMaterial');m.node_tree.links.new(e.outputs[0],o.inputs[0])
    return m

cyan=emit('Faixas · borda ciano',(.015,.48,1),5)
violet=emit('Faixas · borda violeta',(.35,.03,1),4)
dim=emit('Faixas · gravação discreta',(.025,.18,.55),.85)
ice=emit('Faixas · terminais',(.2,.75,1),4)

def plate_material(name,color):
    m=bpy.data.materials.new(name);m.use_nodes=True
    n=m.node_tree.nodes;n.clear();l=m.node_tree.links
    t=n.new('ShaderNodeBsdfTransparent')
    g=n.new('ShaderNodeBsdfGlass');g.inputs['Color'].default_value=(*color,1);g.inputs['Roughness'].default_value=.16;g.inputs['IOR'].default_value=1.1
    mix=n.new('ShaderNodeMixShader');mix.inputs[0].default_value=.12
    l.new(t.outputs[0],mix.inputs[1]);l.new(g.outputs[0],mix.inputs[2])
    e=n.new('ShaderNodeEmission');e.inputs[0].default_value=(*color,1);e.inputs[1].default_value=.23
    tint=n.new('ShaderNodeMixShader');tint.inputs[0].default_value=.16
    l.new(mix.outputs[0],tint.inputs[1]);l.new(e.outputs[0],tint.inputs[2])
    o=n.new('ShaderNodeOutputMaterial');l.new(tint.outputs[0],o.inputs[0])
    return m

plate_blue=plate_material('Placa · vidro ciano',(.04,.35,.8))
plate_purple=plate_material('Placa · vidro violeta',(.25,.035,.7))

def line(name,points,mat,width,c,parent):
    cu=bpy.data.curves.new(name,'CURVE');cu.dimensions='3D';cu.bevel_depth=width;cu.bevel_resolution=1
    sp=cu.splines.new('POLY');sp.points.add(len(points)-1)
    for p,co in zip(sp.points,points):p.co=(*co,1)
    ob=bpy.data.objects.new(name,cu);c.objects.link(ob);ob.parent=parent;cu.materials.append(mat)
    return ob

# Radius, ribbon width, axis orientation, angular start/end.
specs=[
    (1.40,.16,(38,8,-24),0,360),
    (1.96,.24,(-18,26,32),10,190),
    (2.55,.27,(12,-15,-12),0,360),
    (3.12,.20,(-24,-8,18),175,355),
]
records=[]
styles=('Energia', 'Dados', 'Circuitos', 'Grade externa')
for idx,(r,width,angles,start,end) in enumerate(specs):
    rng=Random(714+idx)
    c=bpy.data.collections.new('%02d · %s'%(idx+3,styles[idx]))
    scene.collection.children.link(c)
    parent=bpy.data.objects.new('Eixo independente %d'%(idx+1),None);c.objects.link(parent)
    parent.rotation_euler=tuple(math.radians(a) for a in angles)
    parent['radius']=r;parent['arc_degrees']=end-start;parent['ribbon_width']=width
    accent=cyan if idx%2==0 else violet
    glass=plate_blue if idx%2==0 else plate_purple
    count=18 if end-start==360 else 9
    weights=[rng.uniform(.55,1.55) for _ in range(count)]
    boundaries=[start]
    for weight in weights:
        boundaries.append(boundaries[-1]+(end-start)*weight/sum(weights))
    def point(a,z,offset=0):
        a=math.radians(a)
        # A flared, curved lamina: radial breadth plus axial depth. This gives
        # the hologram a readable face, rather than an edge-on cylindrical belt.
        radial=r+offset+z*.85
        return (radial*math.cos(a),radial*math.sin(a),z*.6-z*z*.3)
    if idx != 2:
        sectors = ((0, 73), (89, 162), (179, 255), (277, 360)) if idx == 0 else ((0, 42), (47, 114), (120, 180))
        for sector, (lo, hi) in enumerate(sectors):
            a, b = start+lo, start+hi
            if idx == 0:
                for strand in range(5):
                    points = []
                    for j in range(121):
                        t = j/120
                        envelope = math.sin(math.pi*t)
                        z = (strand-2)*.021 + .032*envelope*math.sin(t*12+strand*.8)
                        points.append(point(a+(b-a)*t,z))
                    ob = line('Fluxo de energia',points,cyan if strand==2 else dim,.004 if strand==2 else .0016,c,parent)
                    for j, p in enumerate(ob.data.splines[0].points):
                        p.radius = max(.06,math.sin(math.pi*j/120)**.65)
            elif idx == 1:
                for cell in range(4):
                    x = a+(b-a)*cell/4
                    span = (b-a)/4*.79
                    for row in range(3):
                        z = width*(row-1)*.25
                        for bit in range(7):
                            if rng.random() < .34:
                                continue
                            left = x+span*bit/7
                            right = left+span*.10
                            line('Bloco de dados',[point(left,z),point(right,z)],violet if row==1 else dim,.003,c,parent)
                    line('Separador de registros',[point(x,-width*.48),point(x,width*.48)],violet,.0017,c,parent)
            else:
                for rail in (-.45,-.15,.16,.46):
                    line('Longarina da grade',[point(a+(b-a)*j/120,width*rail) for j in range(121)],dim,.0018,c,parent)
                for j in range(int(b-a)//3):
                    x = a+j*3
                    line('Travessa aberta',[point(x,-width*.45),point(x+1.5,width*.46)],violet if j%6==0 else dim,.0022,c,parent)
                line('Acento da grade',[point(a+(b-a)*j/100,width*.46) for j in range(27,52)],violet,.0035,c,parent)
        records.append({'style':styles[idx],'radius':r,'width':width,'span_degrees':end-start,'axis_degrees':angles,'plates':0})
        continue
    for rail in range(3):
        z=width*(-.40+rail*.34)
        offset=(rail%3)*.025
        for sector in range(4):
            a=start+(end-start)*sector/4+rng.uniform(2,8)
            b=start+(end-start)*(sector+1)/4-rng.uniform(9,21)
            pts=[point(a+(b-a)*j/180,z,offset) for j in range(181)]
            line('Barramento fragmentado',pts,accent if rail==1 and sector%2==0 else dim,.0028 if rail==1 else .0011,c,parent)
    for tile in range(count):
        a=boundaries[tile]+rng.uniform(.3,1.5);b=boundaries[tile+1]-rng.uniform(1,3)
        low=-width*rng.uniform(.15,.45)
        high=width*rng.uniform(.20,.58)
        # Staggered glass panels with notched corners and multiple depths.
        offset=rng.uniform(-.025,.045)
        verts=[point(a+(b-a)*j/10,z+(width*.10 if j in (0,1,9,10) else 0),offset) for z in (low,high) for j in range(11)]
        faces=[(j,j+1,j+12,j+11) for j in range(10)]
        mesh=bpy.data.meshes.new('Placa curva');mesh.from_pydata(verts,[],faces)
        ob=bpy.data.objects.new('Placa %d.%02d'%(idx+1,tile+1),mesh);c.objects.link(ob);ob.parent=parent;mesh.materials.append(glass)
        for face in mesh.polygons:face.use_smooth=True
        # Shorter laminated overlays break the repeated rectangular silhouette.
        if tile%3 != 1:
            aa=a+(b-a)*.15;bb=a+(b-a)*.72
            lo=low+width*.22;hi=high+width*.10
            vv=[point(aa+(bb-aa)*j/10,z,offset+.045) for z in (lo,hi) for j in range(11)]
            mm=bpy.data.meshes.new('Lâmina sobreposta');mm.from_pydata(vv,[],faces)
            oo=bpy.data.objects.new('Lâmina escalonada',mm);c.objects.link(oo);oo.parent=parent;mm.materials.append(glass)
            for zz in (lo,hi):
                line('Recorte da lâmina',[point(aa+(bb-aa)*j/40,zz,offset+.048) for j in range(41)],dim,.0012,c,parent)
        for z in (low,high):
            line('Borda interrompida da placa',[point(a+(b-a)*j/32,z,offset+.003) for j in range(4,29)],accent if tile%5==0 else dim,.0015,c,parent)
        if tile%3==0:
            line('Junta transversal',[point(a,low,offset+.003),point(a,high,offset+.003)],dim,.0012,c,parent)
        # Etched paths occupy the ribbon itself, never the gaps between bands.
        lanes=12 if tile%4==0 else 4 if tile%3 else 7
        for lane in range(lanes):
            z=low+(high-low)*(lane+1)/(lanes+2)
            aa=a+rng.uniform(.5,3);bb=b-rng.uniform(.5,2)
            bend=rng.uniform(.28,.65)
            # Curved samples follow the plate; short lateral jogs form traces.
            pts=[point(aa+(bb-aa)*j/32,z+(width*.025 if j/32>bend else 0),offset+.006) for j in range(33)]
            line('Circuito gravado',pts,accent if lane in (2,6) and tile%4==0 else dim,.0011,c,parent)
        # Sparse printed chips and micro-contact combs supply the architectural
        # density of the reference without a free-floating particle cloud.
        for chip in range(2 if tile%4==0 else 0):
            aa=a+2+chip*3;bb=aa+1.2
            z=low+(high-low)*(.3+chip*.3)
            pts=[point(aa,z,offset+.009),point(bb,z,offset+.009),point(bb,z+.025,offset+.009),point(aa,z+.025,offset+.009),point(aa,z,offset+.009)]
            line('Módulo impresso',pts,accent,.0016,c,parent)
        # Short rectangular contact strips replace free-floating particles.
        if tile%3==0:
            for k in range(14):
                aa=a+2+k*.32
                line('Contato integrado',[point(aa,low+.02,offset+.008),point(aa,low+width*.18,offset+.008)],ice if k%4==0 else accent,.0016,c,parent)
        if tile%5==0:
            # A short thickened signal trace, integrated into the ribbon.
            line('Trecho luminoso',[point(a+2+j*.045,high-.015,offset+.012) for j in range(36)],ice,.004,c,parent)
        if tile%4==0:
            # Transverse etched pathways form local architectural clusters.
            for k in range(5):
                aa=a+(b-a)*.55+k*.5
                line('Circuito transversal',[point(aa,low+.015,offset+.008),point(aa,high-.025,offset+.008)],accent if k==2 else dim,.0012,c,parent)
    records.append({'style':styles[idx],'radius':r,'width':width,'span_degrees':end-start,'axis_degrees':angles,'plates':count})

# Larger nested volumes bridge the empty space without adding particles.
# Partial surface contours describe spherical shells, not flat planar rings.
shell_radii=(.95,1.65,2.24)
veil_color=(.035,.21,.65)
def veil_material():
    mat=bpy.data.materials.new('Camadas · azul translúcido');mat.use_nodes=True
    n=mat.node_tree.nodes;n.clear();links=mat.node_tree.links
    transparent=n.new('ShaderNodeBsdfTransparent')
    glow=n.new('ShaderNodeEmission')
    glow.inputs[0].default_value=(*veil_color,1)
    glow.inputs[1].default_value=.14
    facing=n.new('ShaderNodeLayerWeight')
    power=n.new('ShaderNodeMath');power.operation='POWER';power.inputs[1].default_value=1.5
    links.new(facing.outputs['Facing'],power.inputs[0])
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=3;noise.inputs['Detail'].default_value=1
    coords=n.new('ShaderNodeTexCoord');links.new(coords.outputs['Generated'],noise.inputs['Vector'])
    fade=n.new('ShaderNodeMath');fade.operation='MULTIPLY'
    links.new(power.outputs[0],fade.inputs[0]);links.new(noise.outputs['Fac'],fade.inputs[1])
    base=n.new('ShaderNodeMath');base.operation='ADD';base.inputs[1].default_value=.015
    links.new(fade.outputs[0],base.inputs[0])
    opacity = n.new('ShaderNodeMath')
    opacity.operation = 'MULTIPLY'
    opacity.inputs[1].default_value = .85
    links.new(base.outputs[0], opacity.inputs[0])
    mix = n.new('ShaderNodeMixShader')
    links.new(opacity.outputs[0], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(glow.outputs[0], mix.inputs[2])
    out=n.new('ShaderNodeOutputMaterial');links.new(mix.outputs[0],out.inputs[0])
    return mat

material=veil_material()
for index,radius in enumerate(shell_radii):
    c=bpy.data.collections.new('Volume intermediário %d'%(index+1));scene.collection.children.link(c)
    parent=bpy.data.objects.new('Camada esférica %d'%(index+1),None);c.objects.link(parent)
    parent['radius']=radius
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=radius)
    shell=bpy.context.object
    shell.name='Esfera translúcida %d'%(index+1)
    for old in list(shell.users_collection):
        old.objects.unlink(shell)
    c.objects.link(shell)
    shell.parent=parent
    shell.data.materials.append(material)
    for face in shell.data.polygons:
        face.use_smooth=True

particle_collection = bpy.data.collections.new('Partículas luminosas')
scene.collection.children.link(particle_collection)
particle_rng = Random(1107)
particle_blue = emit('Partícula azul', (.05,.38,1), 1.7)
particle_violet = emit('Partícula violeta', (.42,.10,1), 1.8)

def particle_group(name, centers, material):
    # One editable mesh per layer, with an octahedron for each light point.
    vertices, faces = [], []
    for center in centers:
        size = particle_rng.uniform(.005,.012)
        first = len(vertices)
        for axis in range(3):
            delta = Vector(tuple(size if i == axis else 0 for i in range(3)))
            vertices.extend((center+delta,center-delta))
        rim = (0,2,1,3)
        for a,b in zip(rim,rim[1:]+rim[:1]):
            faces.extend(((first+4,first+a,first+b),(first+5,first+b,first+a)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces)
    obj = bpy.data.objects.new(name,mesh)
    particle_collection.objects.link(obj)
    mesh.materials.append(material)
    obj['count'] = len(centers)

for index, radius in enumerate((CORE_SCALE*.83,*shell_radii)):
    centers = []
    for _ in range(18+index*9):
        azimuth = particle_rng.uniform(0,math.tau)
        height = particle_rng.uniform(-1,1)
        ring = math.sqrt(1-height*height)
        centers.append(radius*Vector((ring*math.cos(azimuth),ring*math.sin(azimuth),height)))
    name = 'Núcleo · partículas' if index == 0 else f'Esfera {index} · partículas'
    particle_group(name,centers,particle_violet if index == 0 else particle_blue)

for index,(radius,width,angles,start,end) in enumerate(specs):
    rotation = Euler(tuple(math.radians(angle) for angle in angles)).to_matrix()
    portions = ((0,73),(89,162),(179,255),(277,360)) if index == 0 else ((0,42),(47,114),(120,180)) if end-start == 180 else ((0,360),)
    centers = []
    for low,high in portions:
        for _ in range(max(4,round((high-low)/12))):
            angle = math.radians(start+particle_rng.uniform(low+2,high-2))
            z = particle_rng.uniform(-width*.30,width*.30)
            radial = radius+.012+z*.85
            centers.append(rotation@Vector((radial*math.cos(angle),radial*math.sin(angle),z*.6-z*z*.3)))
    particle_group(f'{styles[index]} · partículas',centers,particle_blue if index%2==0 else particle_violet)

camera=scene.camera
def aim(location):
    camera.location=location
    camera.rotation_euler=(-camera.location).to_track_quat('-Z','Y').to_euler()
aim((.25,-.4,13.8))
scene.camera.data.lens=58
assert set(original).issubset(bpy.data.objects.keys())
assert len(bpy.data.actions)==0
assert sum(r['span_degrees']==180 for r in records)==2
assert not any(n.type=='TEX_IMAGE' for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes)
(OUT/'validation.json').write_text(json.dumps({'source':str(SOURCE),'bands':records,'core_scale':CORE_SCALE,'shell_radii':shell_radii,'animations':0,'image_textures':0,'original_objects_retained':len(original)},indent=2),encoding='utf8')
scene.render.filepath=str(OUT/'bands-front.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'synapse-core-bands.blend'))
bpy.ops.render.render(write_still=True)
aim((7,-3,11.4));scene.render.filepath=str(OUT/'bands-angle.png');bpy.ops.render.render(write_still=True)

