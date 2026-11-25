"""Raposa + suporte para os 4 pontos do Zumo 2040. Executar deste diretorio ou via caminho.
Dependencias: trimesh, manifold3d, numpy, scipy, matplotlib, networkx, lxml.
A geometria da raposa vem das copias dos arquivos v1 na pasta fontes.
"""
from pathlib import Path
import json, zipfile, hashlib
import xml.etree.ElementTree as ET
import numpy as np
import trimesh as tm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon
OUT=Path(__file__).resolve().parent
P=json.loads((OUT/'parametros.json').read_text())
M=P['mount']; F=P['fox']; T=M['plate_thickness']; H=M['spacer_height']
HOLES=M['front_holes']+M['rear_holes']
R=M['hole_diameter']/2
C={'base':'#C91A38','vermelho':'#CA1536','branco':'#F4EFE5','preto':'#24252C','espacador':'#CBC4B9','pcb':'#30383C','oled':'#44445D','metal':'#B4B9BD'}

def union(items): return tm.boolean.union(items,engine='manifold')
def diff(mesh,items): return tm.boolean.difference([mesh]+items,engine='manifold')
def shift(mesh,xyz):
    mesh=mesh.copy();mesh.apply_translation(xyz);return mesh

def box(size,center):return shift(tm.creation.box(size),center)
def cyl(r,h,center=(0,0,0),n=64):return shift(tm.creation.cylinder(r,h,sections=n),[center[0],center[1],center[2]+h/2])
def bar(p,q,w,z,h):
    return tm.convex.convex_hull(np.vstack([cyl(w/2,h,(*p,z),32).vertices,cyl(w/2,h,(*q,z),32).vertices]))
def round_rect(w,d,r,center,z,h):
    return tm.convex.convex_hull(np.vstack([cyl(r,h,(center[0]+sx*(w/2-r),center[1]+sy*(d/2-r),z),24).vertices for sx in [-1,1] for sy in [-1,1]]))

# Estrutura em U: sem travessa traseira para manter botoes e USB abertos.
rails=[]
for s in [-1,1]:
    path=[(s*25,0),(s*25.5,40),(s*22,54),(s*22,57),(s*27.5,63)]
    rails.extend(bar(a,b,M['rail_width'],0,T) for a,b in zip(path,path[1:]))
rails.extend([bar((-25,9),(25,9),6,0,T),round_rect(24,18,2,(0,9),0,T)])
rails.extend(cyl(M['pad_diameter']/2,T,(*p,0)) for p in HOLES)
blank=union(rails)
base_flat=diff(blank,[cyl(R,T+2,(*p,-1)) for p in HOLES])
# Chanfro superior do pino para facilitar o encaixe sem forcar PLA.
peg=union([box([F['peg_width'],F['peg_depth'],F['peg_height']-.5],(0,F['center_y'],T+(F['peg_height']-.5)/2)),
    tm.convex.convex_hull(np.vstack([box([8,6,.01],(0,F['center_y'],T+2.5)).vertices,box([7,5,.01],(0,F['center_y'],T+3-.005)).vertices]))])
base=union([base_flat,peg])

# Cabeça com alojamento inferior e pontas truncadas para reduzir fragilidade.
head_original=tm.load_mesh(OUT/'fontes/cabeca_v1.stl')
head_color_scene=tm.load(OUT/'fontes/cabeca_v1_cores.3mf')
clear=F['socket_xy_clearance_per_side']; pocket_depth=F['peg_height']+F['socket_extra_depth']
pocket=box([F['peg_width']+2*clear,F['peg_depth']+2*clear,pocket_depth+1],(0,0,(pocket_depth-1)/2))
cap=box([100,100,40],(0,0,F['trimmed_height']+20))
head=diff(head_original,[pocket,cap])
head_parts={n:diff(m,[pocket,cap]) for n,m in head_color_scene.geometry.items()}
spacer=diff(cyl(M['spacer_diameter']/2,H),[cyl(R,H+2,(0,0,-1))])
shims={str(h):diff(cyl(3,h),[cyl(R,h+2,(0,0,-1))]) for h in [.2,.4,.6,.8,1.0,1.2]}
# Cupom: três furos, alojamento do encaixe e pino separado.
coupon=diff(round_rect(40,14,1,(0,0),0,4.8),[cyl(d/2,7,(x,0,-1)) for x,d in [(-15,2.4),(-8,2.6),(-1,2.8)]]+[box([8.4,6.4,4],(10,0,3.4))])
coupon_peg=union([box([12,10,1.6],(30,0,.8)),box([8,6,3],(30,0,3.1))])
coupon=tm.util.concatenate([coupon,coupon_peg])
# Gabarito fino da furação: só para prova, não é suporte estrutural.
gauge=base_flat.copy();gauge.vertices[:,2]*=.8/T
exports={'base_4_parafusos.stl':base,'cabeca_raposa_encaixe.stl':head,'espacador_12mm_imprimir_4.stl':spacer,
         'teste_furos_encaixe.stl':coupon,'gabarito_furacao_08mm.stl':gauge}
exports.update({f'calco_{k.replace(".","p")}mm.stl':v for k,v in shims.items()})
for name,mesh in exports.items():mesh.export(OUT/name)

# 3MF para impressão: todas as pecas apoiadas em Z=0; uma cabeça em três cores.
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'; ET.register_namespace('',NS)
def elem(parent,tag,attrs=None,text=None):
    e=ET.SubElement(parent,'{'+NS+'}'+tag,attrs or {})
    if text is not None:e.text=text
    return e
model=ET.Element('{'+NS+'}model',{'unit':'millimeter'})
elem(model,'metadata',{'name':'Title'},'Raposa Zumo v2 - conjunto para PLA, sem perfil de impressora')
resources=elem(model,'resources');materials=elem(resources,'basematerials',{'id':'1'})
for key in ['base','vermelho','branco','preto','espacador']:elem(materials,'base',{'name':key,'displaycolor':C[key]+'FF'})
def object_mesh(oid,name,mesh,color_index):
    ob=elem(resources,'object',{'id':str(oid),'type':'model','name':name,'pid':'1','pindex':str(color_index)})
    geo=elem(ob,'mesh');vs=elem(geo,'vertices');fs=elem(geo,'triangles')
    for v in mesh.vertices:elem(vs,'vertex',dict(zip(('x','y','z'),(f'{x:.12g}' for x in v))))
    for f in mesh.faces:elem(fs,'triangle',dict(zip(('v1','v2','v3'),(str(int(x)) for x in f))))
object_mesh(2,'base_4_parafusos',base,0)
for oid,(key,m) in enumerate(head_parts.items(),3):object_mesh(oid,'cabeca_'+key,m,['base','vermelho','branco','preto','espacador'].index(key))
ob=elem(resources,'object',{'id':'6','type':'model','name':'cabeca_raposa_encaixe'});com=elem(ob,'components')
for oid in [3,4,5]:elem(com,'component',{'objectid':str(oid)})
object_mesh(7,'espacador_12mm',spacer,4)
build=elem(model,'build')
for oid,xyz in [(2,(32,4.5,0)),(6,(88,24.5,0))]+[(7,(x,y,0)) for x in [80,94] for y in [52,65]]:
    elem(build,'item',{'objectid':str(oid),'transform':'1 0 0 0 1 0 0 0 1 '+' '.join(map(str,xyz))})
with zipfile.ZipFile(OUT/'conjunto_PLA_para_fatiar.3mf','w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))

# Dados de verificação: arquivos reabertos, continuidade, furos e envelopes.
report={'revision':P['revision'],'files':{},'holes_xy_mm':HOLES,'source_dimensions':P['source_dimensions'],
        'hole_diameter_mm':2*R,'head_socket_mm':[8.4,6.4,pocket_depth],
        'plate_underface_above_level_seats_mm':H,'head_top_above_level_seats_mm':H+T+F['trimmed_height'],
        'sliced':False,'physical_fit_tested':False,'blade_thickness_verified':False}
for name in exports:
    mesh=tm.load_mesh(OUT/name)
    assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0,name
    expected=2 if name=='teste_furos_encaixe.stl' else 1
    assert len(mesh.split())==expected,(name,len(mesh.split()))
    report['files'][name]={'bounds_mm':mesh.bounds.tolist(),'watertight':bool(mesh.is_watertight),'components':len(mesh.split()),'volume_mm3':float(mesh.volume)}
for p in HOLES:
    probe=cyl(R-.03,T+1,(*p,-.5))
    hit=tm.boolean.intersection([base,probe],engine='manifold')
    assert hit.is_empty or abs(hit.volume)<1e-7
    # Continuidade de parede anular junto ao furo.
    ring=diff(cyl(3,T,(*p,0)),[cyl(R+.03,T+2,(*p,-1))])
    overlap=tm.boolean.intersection([base,ring],engine='manifold')
    assert np.isclose(overlap.volume,ring.volume,rtol=1e-5)
# OLED: x+-17.7, y20..53.5, z0..9.8 (PDF). Verifica volume e visibilidade vertical.
oled_box=box([35.4,33.5,9.8],(0,36.75,4.9))
assembled_head=shift(head,[0,F['center_y'],H+T]);assembled_base=shift(base,[0,0,H])
model_union=union([assembled_base,assembled_head])
for label,envelope in [('oled_volume',oled_box),('oled_vista_vertical',box([35.4,33.5,100],(0,36.75,50)) )]:
    hit=tm.boolean.intersection([model_union,envelope],engine='manifold')
    report[label+'_intersection_mm3']=0 if hit.is_empty else float(hit.volume)
    assert hit.is_empty or abs(hit.volume)<1e-7,label
# Verificar encaixe sem interferência e acesso axial aos quatro parafusos.
hit=tm.boolean.intersection([assembled_base,assembled_head],engine='manifold')
assert hit.is_empty or abs(hit.volume)<1e-5
report['peg_head_interference_mm3']=0 if hit.is_empty else float(hit.volume)
for p in HOLES:
    access=cyl(3.5,70,(*p,H+T+.02))
    hit=tm.boolean.intersection([model_union,access],engine='manifold')
    assert hit.is_empty or abs(hit.volume)<1e-7
report['screwdriver_clearance_diameter_mm']=7
assert F['center_y']+head.bounds[1,1] < 20
report['gap_fox_to_oled_y_mm']=float(20-(F['center_y']+head.bounds[1,1]))
scene=tm.load(OUT/'conjunto_PLA_para_fatiar.3mf')
assert all(m.is_watertight for m in scene.geometry.values())
assert len(scene.graph.nodes_geometry)==8 # base + três cores da cabeça + quatro espaçadores
report['three_mf_geometry_count']=len(scene.geometry)
report['three_mf_mesh_instances']=len(scene.graph.nodes_geometry)
report['source_sha256']={}
for source in ['zumo-2040-main-board-dimensions.pdf','zumo-2040-robot-dimensions.pdf']:
    p=OUT/'fontes'/source
    report['source_sha256'][source]=hashlib.sha256(p.read_bytes()).hexdigest()
(OUT/'verificacao_v2.json').write_text(json.dumps(report,indent=2)+'\n')

# Render de malhas com buffer de profundidade; placa simplificada só como referência.
def render(items,az=-65,el=33,size=1000,span=108,center=(0,26,18)):
    az,el=np.radians([az,el]);view=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0]);up=np.cross(view,right)
    img=np.tile(matplotlib.colors.to_rgb('#F4F2EE'),(size,size,1));depth=np.full((size,size),-np.inf)
    light=np.array([-.4,-.8,1]);light/=np.linalg.norm(light)
    for mesh,color in items:
        xyz=mesh.vertices-np.array(center);screen=np.column_stack([xyz@right,-xyz@up])/span*size+size/2;zz=xyz@view
        color=np.array(matplotlib.colors.to_rgb(color));shades=.66+.34*np.clip(mesh.face_normals@light,0,1)
        for face,shade in zip(mesh.faces,shades):
            pts=screen[face];zs=zz[face];lo=np.maximum(np.floor(pts.min(0)).astype(int),0);hi=np.minimum(np.ceil(pts.max(0)).astype(int),size-1)
            if np.any(hi<lo):continue
            x,y=np.meshgrid(np.arange(lo[0],hi[0]+1)+.5,np.arange(lo[1],hi[1]+1)+.5)
            x0,y0=pts[0];x1,y1=pts[1];x2,y2=pts[2];d=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
            if abs(d)<1e-8:continue
            a=((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/d;b=((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/d;c=1-a-b;z=a*zs[0]+b*zs[1]+c*zs[2]
            reg=depth[lo[1]:hi[1]+1,lo[0]:hi[0]+1];mask=(a>=-1e-8)&(b>=-1e-8)&(c>=-1e-8)&(z>reg+1e-7)
            reg[mask]=z[mask];img[lo[1]:hi[1]+1,lo[0]:hi[0]+1][mask]=color*shade
    return np.clip(img,0,1)

pcb=box([66,82.8,1.57],(0,35.1,-.785))
assembly=[(pcb,C['pcb']),(oled_box,C['oled']),(assembled_base,C['base'])]
assembly += [(shift(m,[0,F['center_y'],H+T]),C[n]) for n,m in head_parts.items()]
assembly += [(shift(spacer,[*p,0]),C['espacador']) for p in HOLES]
assembly += [(cyl(2.25,1.6,(*p,H+T)),C['metal']) for p in HOLES]
# Comandos traseiros e USB em posição esquemática/documental.
for x in [-13.9,-1.3,15.2]:assembly.append((box([3.2,4,2],(x,67.6,1)),C['metal']))
assembly.append((box([8.9,7,3.2],(7.35,73,1.6)),C['metal']))
assembly.append((box([3,4.5,3],(28.2,56.9,1.5)),C['metal']))
fig,ax=plt.subplots(1,2,figsize=(12.6,7.5),facecolor='#F4F2EE')
for a,im,title in zip(ax,[render(assembly),render([(assembled_base,C['base'])]+[(shift(spacer,[*p,0]),C['espacador']) for p in HOLES],az=-65,el=43,span=95,center=(0,30,5))],['CONJUNTO SOBRE A PLACA','BASE ABERTA + 4 ESPAÇADORES']):
    a.imshow(im);a.axis('off');a.set_title(title,fontsize=10,color='#595451')
fig.text(.06,.92,'RAPOSA / ZUMO 2040',fontsize=25,weight='bold',color='#25252C')
fig.text(.06,.86,'Fixação em quatro pontos · cabeça de 40 mm · impressão em PLA',fontsize=12,color='#595451')
fig.text(.06,.07,'Placa e componentes simplificados para referência. Parafusos #2-56 mais longos.\nConferir nivelamento das abas da lâmina frontal e testar a montagem antes do uso.',fontsize=10,color='#595451',linespacing=1.6)
fig.subplots_adjust(left=.02,right=.98,bottom=.13,top=.79,wspace=.04)
fig.savefig(OUT/'previa_montagem_v2.png',dpi=170);plt.close(fig)
# Vista cotada, medida a partir de eixo dos furos, não das bordas do modelo.
fig,ax=plt.subplots(figsize=(8,10),facecolor='white')
ax.set_aspect('equal');ax.set_xlim(-45,45);ax.set_ylim(82,-20);ax.axis('off')
for tri in base_flat.triangles:
    if np.allclose(tri[:,2],T):ax.fill(tri[:,0],tri[:,1],color='#DCC8CB',edgecolor='#DCC8CB',linewidth=.25)
ax.add_patch(Rectangle((-17.7,20),35.4,33.5,facecolor='#E4E8EF',edgecolor='#76839A',lw=1.2))
ax.text(0,36.75,'OLED\n35,4 × 33,5 mm',ha='center',va='center',fontsize=11,color='#4F607B')
for x,y in HOLES:
    ax.add_patch(Circle((x,y),R,fill=False,color='#25252C'))
    ax.plot([x-2,x+2],[y,y],color='#25252C',lw=.6);ax.plot([x,x],[y-2,y+2],color='#25252C',lw=.6)
def dim(p,q,label,shift=(0,0)):
    a=np.array(p)+shift;b=np.array(q)+shift
    ax.plot([p[0],a[0]],[p[1],a[1]],color='#777777',lw=.7);ax.plot([q[0],b[0]],[q[1],b[1]],color='#777777',lw=.7)
    ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'<->','color':'#25252C','lw':1})
    c=(a+b)/2;ax.text(c[0]+(2 if a[0]==b[0] else 0),c[1]-(1.8 if a[1]==b[1] else 0),label,ha='left' if a[0]==b[0] else 'center',va='center',fontsize=11)
dim((-25,0),(25,0),'50,0',(0,-11));dim((-27.5,63),(27.5,63),'55,0',(0,10));dim((27.5,0),(27.5,63),'63,0',(9,0))
ax.add_patch(Rectangle((-10,2),20,14,fill=False,edgecolor='#B01735',ls='--',lw=1.2));ax.text(0,9,'encaixe\nda raposa',ha='center',va='center',fontsize=9,color='#A91834')
ax.text(0,-17,'FRENTE / LÂMINA',ha='center',fontsize=12,weight='bold');ax.text(0,80,'TRÁS / USB E BOTÕES',ha='center',fontsize=11,weight='bold')
fig.suptitle('FURAÇÃO E ÁREA LIVRE DO DISPLAY',fontsize=16,weight='bold',y=.97)
fig.text(.12,.04,'Cotas entre centros, em mm. Furos passantes Ø2,6 mm.\nO desenho da base não é uma reprodução do contorno da PCB.',fontsize=10)
fig.savefig(OUT/'furacao_cotada.png',dpi=160);plt.close(fig)
print(json.dumps({'files':len(exports),'base_mm':base.extents.tolist(),'head_mm':head.extents.tolist(),'oled_clear':True,'report':str(OUT/'verificacao_v2.json')},indent=2))
