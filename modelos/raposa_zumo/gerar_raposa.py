"""Cabeça de raposa de 40 mm. Dependências: trimesh manifold3d numpy scipy matplotlib networkx lxml.
Execute: python gerar_raposa.py [largura_em_mm]. Coordenadas: frente = -Y, cima = +Z.
"""
from pathlib import Path
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import trimesh as tm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
WIDTH = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
SCALE = WIDTH / 40
COLORS = {'vermelho': '#CA1536', 'branco': '#F4EFE5', 'preto': '#24252C'}
raw = {k: [] for k in COLORS}

def hull(points, color):
    mesh = tm.convex.convex_hull(np.array(points, dtype=float))
    raw[color].append(mesh)
    return mesh

def mirror(points):
    return [[-x, y, z] for x, y, z in points]

def pair(points, color):
    hull(points, color)
    hull(mirror(points), color)

def octagon(w, d, z, cy=1, chamfer=2):
    return [[x, y+cy, z] for x,y in [(-w+chamfer,-d),(w-chamfer,-d),(w,-d+chamfer),(w,d-chamfer),(w-chamfer,d),(-w+chamfer,d),(-w,d-chamfer),(-w,-d+chamfer)]]

# Base de 20 x 14 mm, assentamento plano, borda superior chanfrada.
hull(octagon(10,7,0)+octagon(10,7,2)+octagon(9,6,3), 'vermelho')
# Pescoço curto e crânio facetado.
hull(octagon(7,5,2)+octagon(8,6,8), 'vermelho')
hull(octagon(7,5,5)+octagon(12,8,10)+octagon(17,9,18)+octagon(15,9,25)+octagon(10,6,30), 'vermelho')
# Orelhas: pontas truncadas de 1,2 mm, resistentes em escala pequena.
pair([[7,-3,26],[16,-3,24],[17,0,39.4],[16.4,0,40],
      [15.8,0,40],[8,6,26],[16,5,26],[16.5,2,39]], 'vermelho')
# Interior branco das orelhas, integrado e ligeiramente saliente.
pair([[9.5,-3.25,28],[14.5,-3.25,27],[16, -0.65,36.8],
      [9.5,-2.1,28],[14.5,-2.1,27],[16,0.5,36.8]], 'branco')
# Bochechas claras, volume que converge para o focinho.
pair([[3,-10,19.7],[13,-9,22],[20,-3.5,19],[17,-6.5,15],
      [13,-7,11],[3,-13,10],[0,-15,12], [5,-16.2,15],
      [13,-11.7,17.5],[18,-7,18.5],[7,-6,13]], 'branco')
# Ponte nasal vermelha, estreita e longa.
hull([[-5,-9,24],[5,-9,24],[-6,-8,19],[6,-8,19],
      [-2.8,-18.4,14.5],[2.8,-18.4,14.5],[0,-16,10],
      [-4,-11,12],[4,-11,12]], 'vermelho')
# Nariz preto com ponta achatada.
hull([[-3.2,-17.5,15.6],[3.2,-17.5,15.6],[-2.6,-20,15.1],
      [2.6,-20,15.1],[0,-20,12.5],[0,-17.2,12]], 'preto')
# Olhos inclinados: cavidade preta larga e pupila em relevo.
eye = [[3.1,-9.55,22.1],[11.5,-9.55,25],[11.1,-9.55,22.7],[4,-9.55,20.9],
       [3.1,-7.1,22.1],[11.5,-7.1,25],[11.1,-7.1,22.7],[4,-7.1,20.9]]
pair(eye, 'preto')
pair([[4.5,-9.85,22],[10.2,-9.85,24],[9.9,-9.85,22.9],[5,-9.85,21.7],
      [4.5,-9.2,22],[10.2,-9.2,24],[9.9,-9.2,22.9],[5,-9.2,21.7]], 'branco')
pair([[7.5,-10.15,22.9],[8.7,-10.15,23.3],[8.6,-10.15,22.2],[7.5,-10.15,21.9],
      [7.5,-9.3,22.9],[8.7,-9.3,23.3],[8.6,-9.3,22.2],[7.5,-9.3,21.9]], 'preto')

# União booleana real: um STL fechado, sem cascas internas sobrepostas.
def union(meshes):
    return tm.boolean.union(meshes, engine='manifold') if len(meshes)>1 else meshes[0].copy()

merged = union([mesh for meshes in raw.values() for mesh in meshes])
merged.apply_scale(SCALE)
merged.export(OUT/'raposa_zumo_40mm.stl')

# Partes de cor sem sobreposição. O branco dos olhos cobre parte da máscara preta.
# Prioridade de superfície: selecionar pela profundidade já modelada, preservando
# a máscara preta atrás do branco; dividir interfaces com operações booleanas.
red = union(raw['vermelho'])
white = union(raw['branco'])
black = union(raw['preto'])
# Subtrair do preto apenas o branco dos olhos, deixando as pupilas à frente.
white_eye = union(raw['branco'][-2:])
black = tm.boolean.difference([black, white_eye], engine='manifold')
white = tm.boolean.difference([white, black], engine='manifold')
red = tm.boolean.difference([red, union(raw['branco']+raw['preto'])], engine='manifold')
parts = {'vermelho':red, 'branco':white, 'preto':black}
for mesh in parts.values():
    mesh.apply_scale(SCALE)

# 3MF padrão, em milímetros, um conjunto com três volumes e cores de referência.
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('', NS)
def element(parent, tag, attrs=None, text=None):
    e=ET.SubElement(parent, '{'+NS+'}'+tag, attrs or {})
    if text is not None: e.text=text
    return e
model=ET.Element('{'+NS+'}model', {'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'pt-BR'})
element(model,'metadata',{'name':'Title'},'Raposa para Zumo — 40 mm')
resources=element(model,'resources')
materials=element(resources,'basematerials',{'id':'1'})
for name,color in COLORS.items(): element(materials,'base',{'name':name,'displaycolor':color+'FF'})
for i,(name,mesh) in enumerate(parts.items()):
    obj=element(resources,'object',{'id':str(i+2),'type':'model','name':name,'pid':'1','pindex':str(i)})
    m=element(obj,'mesh'); verts=element(m,'vertices'); faces=element(m,'triangles')
    for v in mesh.vertices: element(verts,'vertex',dict(zip(('x','y','z'),(f'{x:.12g}' for x in v))))
    for f in mesh.faces: element(faces,'triangle',dict(zip(('v1','v2','v3'),(str(int(x)) for x in f))))
assembly=element(resources,'object',{'id':'5','type':'model','name':'Raposa Zumo'})
components=element(assembly,'components')
for i in range(2,5): element(components,'component',{'objectid':str(i)})
build=element(model,'build'); element(build,'item',{'objectid':'5'})
with zipfile.ZipFile(OUT/'raposa_zumo_40mm_cores.3mf','w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))

# Fonte OpenSCAD com a geometria original e escala editável.
scad=['// Frente = -Y. Unidade: mm. F6 para união, depois exportar STL.',
      'largura = 40;', 'scale([largura/40,largura/40,largura/40]) union() {']
for color, meshes in raw.items():
    for mesh in meshes:
        scad.append(f'color("{COLORS[color]}") polyhedron(points={mesh.vertices.tolist()}, faces={mesh.faces[:,::-1].tolist()}, convexity=10);')
scad.append('}')
(OUT/'raposa_zumo.scad').write_text('\n'.join(scad))

# Renderização ortográfica com buffer de profundidade (oclusão por pixel).
def render(azimuth, elevation, size=900):
    az,el=np.radians([azimuth,elevation])
    view=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0])
    up=np.cross(view,right)
    background=np.array(matplotlib.colors.to_rgb('#F4F2EE'))
    img=np.tile(background,(size,size,1))
    depth=np.full((size,size),-np.inf)
    center=np.array([0,-4,20])*SCALE
    light=np.array([-.4,-.8,1]);light/=np.linalg.norm(light)
    for name,mesh in parts.items():
        xyz=mesh.vertices-center
        screen=np.column_stack([xyz@right, -xyz@up])/(49*SCALE)*size+size/2
        zz=xyz@view
        color=np.array(matplotlib.colors.to_rgb(COLORS[name]))
        shades=.66+.34*np.clip(mesh.face_normals@light,0,1)
        for face,shade in zip(mesh.faces,shades):
            pts=screen[face]; zs=zz[face]
            lo=np.maximum(np.floor(pts.min(axis=0)).astype(int),0)
            hi=np.minimum(np.ceil(pts.max(axis=0)).astype(int),size-1)
            if np.any(hi<lo): continue
            x,y=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
            x0,y0=pts[0];x1,y1=pts[1];x2,y2=pts[2]
            denom=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
            if abs(denom)<1e-8: continue
            w0=((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/denom
            w1=((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/denom
            w2=1-w0-w1
            z=w0*zs[0]+w1*zs[1]+w2*zs[2]
            region=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            mask=(w0>=-1e-8)&(w1>=-1e-8)&(w2>=-1e-8)&(z>region+1e-7)
            region[mask]=z[mask]
            img[lo[1]:hi[1]+1,lo[0]:hi[0]+1][mask]=color*shade
    return np.clip(img,0,1)

fig,axes=plt.subplots(1,2,figsize=(12,7.5),facecolor='#F4F2EE')
for ax,(azim,elev,label) in zip(axes,[(-65,14,'PERSPECTIVA'),(-90,0,'FRENTE')]):
    ax.imshow(render(azim,elev));ax.axis('off')
    ax.set_title(label,fontsize=10,color='#6B6562',pad=5)
fig.text(.07,.92,'RAPOSA / ZUMO',fontsize=25,weight='bold',color='#24252C')
fig.text(.07,.865,f'{WIDTH:g} mm de largura · base plana · volume facetado',fontsize=12,color='#6B6562')
fig.text(.07,.055,'Vermelho, branco e preto como sugestão de acabamento.\nPrévia da geometria 3D; montagem no robô ainda não verificada.',fontsize=10,color='#6B6562',linespacing=1.7)
plt.subplots_adjust(left=.045,right=.955,top=.80,bottom=.15,wspace=.06)
fig.savefig(OUT/'previa_raposa.png',dpi=180,facecolor=fig.get_facecolor())

# Verificação de malha dos arquivos efetivamente exportados.
scene_check=tm.load(OUT/'raposa_zumo_40mm_cores.3mf')
assert len(scene_check.geometry)==3
assert all(m.is_watertight for m in scene_check.geometry.values())
check=tm.load_mesh(OUT/'raposa_zumo_40mm.stl')
report={'dimensions_mm':check.extents.tolist(),'bounds_mm':check.bounds.tolist(),
        'watertight':bool(check.is_watertight),'winding_consistent':bool(check.is_winding_consistent),
        'connected_components':len(check.split()),'volume_mm3':float(check.volume),
        'triangles':len(check.faces),'base_mm':[20*SCALE,14*SCALE],
        'color_volume_sum_mm3':sum(float(m.volume) for m in parts.values()),
        'parts_watertight':{name:bool(m.is_watertight) for name,m in parts.items()},
        'three_mf_reopened_parts_watertight':{name:bool(m.is_watertight) for name,m in scene_check.geometry.items()},
        'printed_or_sliced':False,'mount_fit_verified':False}
assert check.is_watertight and check.is_winding_consistent and len(check.split())==1
assert np.allclose(check.extents[0],WIDTH)
assert all(m.is_watertight for m in parts.values())
assert np.isclose(report['color_volume_sum_mm3'],check.volume,rtol=1e-5)
(OUT/'verificacao.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
