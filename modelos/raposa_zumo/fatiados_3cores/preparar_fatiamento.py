from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json, xml.etree.ElementTree as ET, copy
ROOT=Path(__file__).resolve().parent; PREP=ROOT/'preparacao'; PROFILES=PREP/'perfis';PROFILES.mkdir(exist_ok=True)
SRC=ROOT.parent/'v2_parafusos/conjunto_PLA_para_fatiar.3mf'
BBL=Path('/var/lib/flatpak/app/com.bambulab.BambuStudio/current/active/files/share/BambuStudio/profiles/BBL')
index={}
for file in BBL.rglob('*.json'):
    try:
        d=json.loads(file.read_text())
        if 'name' in d:index[d['name']]=d
    except (ValueError,UnicodeDecodeError):pass

def resolve(name):
    d=index[name];out={}
    if d.get('inherits'):out.update(resolve(d['inherits']))
    for inc in d.get('include',[]):out.update(resolve(inc))
    out.update(d)
    for k in ['inherits','include']:out.pop(k,None)
    return out

colors=['#CA1536','#F4EFE5','#24252C'];names=['Vermelho','Branco','Preto']
purge=['0','650','350','450','0','350','600','800','0']
variants=[('P2S_04','P2S','0.4','0.16mm High Quality @BBL P2S'),('P2S_06','P2S','0.6','0.18mm Balanced Quality @BBL P2S 0.6 nozzle'),('X1C_04','X1 Carbon','0.4','0.16mm High Quality @BBL X1C'),('X1C_06','X1 Carbon','0.6','0.18mm Standard @BBL X1C 0.6 nozzle')]
for tag,printer,nozzle,process in variants:
    out=ROOT/tag;out.mkdir(exist_ok=True)
    machine_name=f'Bambu Lab {printer} {nozzle} nozzle'
    m=resolve(machine_name);m['curr_bed_type']='Textured PEI Plate'
    m['printer_settings_id']=machine_name
    p=resolve(process);p.update({'print_settings_id':f'Raposa Zumo {tag} PLA 3 cores','wall_loops':'4','wall_generator':'arachne',
        'sparse_infill_density':'15%','sparse_infill_pattern':'gyroid','top_shell_layers':'6','bottom_shell_layers':'5',
        'enable_prime_tower':'1','prime_tower_width':'40','prime_tower_brim_width':'3','prime_volume':'45',
        'enable_support':'0','support_type':'tree(auto)','support_on_build_plate_only':'1','bridge_no_support':'1',
        'support_filament':'1','support_interface_filament':'1','support_top_z_distance':'0.2','support_bottom_z_distance':'0.2',
        'support_object_xy_distance':'0.35','support_interface_top_layers':'3','support_threshold_angle':'30',
        'flush_into_infill':'0','flush_into_objects':'0','flush_into_support':'0','brim_type':'outer_only','brim_width':'3',
        'brim_object_gap':'0.1','outer_wall_speed':['45'],'inner_wall_speed':['100'],'top_surface_speed':['60'],
        'default_acceleration':['3000'],'outer_wall_acceleration':['1000'],'enable_arc_fitting':'0'})
    for kind,d in [('machine',m),('process',p)]: (PROFILES/f'{tag}_{kind}.json').write_text(json.dumps(d,indent=2))
    fila_name='Generic PLA @BBL P2S' if printer=='P2S' else 'Generic PLA'
    fila=resolve(fila_name)
    for i,(color,name) in enumerate(zip(colors,names),1):
        f=copy.deepcopy(fila);f['filament_colour']=[color];f['filament_settings_id']=[fila_name]
        f['filament_is_support']=['0']
        (PROFILES/f'{tag}_PLA_{i}.json').write_text(json.dumps(f,indent=2))

# Projeto nativo Bambu: extrusor associado a cada volume; seis objetos físicos.
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';PN='http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
ET.register_namespace('',NS);ET.register_namespace('p',PN)
def el(p,t,attrs=None,text=None):
    e=ET.SubElement(p,'{'+NS+'}'+t,attrs or {})
    if text is not None:e.text=text
    return e
with ZipFile(SRC) as z: source=ET.fromstring(z.read('3D/3dmodel.model'))
source_obj={int(o.attrib['id']):o for o in source.find('{'+NS+'}resources').findall('{'+NS+'}object')}
meshes={1:copy.deepcopy(source_obj[2].find('{'+NS+'}mesh')),2:copy.deepcopy(source_obj[3].find('{'+NS+'}mesh')),3:copy.deepcopy(source_obj[4].find('{'+NS+'}mesh')),4:copy.deepcopy(source_obj[5].find('{'+NS+'}mesh')),5:copy.deepcopy(source_obj[7].find('{'+NS+'}mesh'))}
# Volume bloqueador dentro da cavidade inferior da cabeça.
block=ET.Element('{'+NS+'}mesh');vs=el(block,'vertices');ts=el(block,'triangles')
verts=[(x,y,z) for z in [-.1,3.6] for y in [-3.3,3.3] for x in [-4.3,4.3]]
for x,y,z in verts:el(vs,'vertex',{'x':str(x),'y':str(y),'z':str(z)})
for f in [(0,2,1),(1,2,3),(4,5,6),(5,7,6),(0,1,4),(1,5,4),(2,6,3),(3,6,7),(0,4,2),(2,4,6),(1,3,5),(3,7,5)]:el(ts,'triangle',dict(zip(['v1','v2','v3'],map(str,f))))
meshes[6]=block
geo=ET.Element('{'+NS+'}model',{'unit':'millimeter'});res=el(geo,'resources')
for oid,mesh in meshes.items():el(res,'object',{'id':str(oid),'type':'model'}).append(mesh)
root=ET.Element('{'+NS+'}model',{'unit':'millimeter','requiredextensions':'p','xmlns:BambuStudio':'http://schemas.bambulab.com/package/2021'})
el(root,'metadata',{'name':'Application'},'BambuStudio-02.09.01.70');el(root,'metadata',{'name':'BambuStudio:3mfVersion'},'1')
el(root,'metadata',{'name':'Title'},'Raposa Zumo v2 - PLA vermelho branco preto')
res=el(root,'resources')
for oid,parts in [(10,[1]),(20,[2,3,4,6]),(30,[5])]:
    ob=el(res,'object',{'id':str(oid),'type':'model'});comp=el(ob,'components')
    for pid in parts:el(comp,'component',{'objectid':str(pid),'{'+PN+'}path':'/3D/Objects/objetos.model','transform':'1 0 0 0 1 0 0 0 1 0 0 0'})
placements=[(10,72,85),(20,143,106),(30,130,139),(30,149,139),(30,130,156),(30,149,156)]
build=el(root,'build')
for oid,x,y in placements:el(build,'item',{'objectid':str(oid),'transform':f'1 0 0 0 1 0 0 0 1 {x} {y} 0','printable':'1'})
config=ET.Element('config')
def md(parent,key,value):ET.SubElement(parent,'metadata',{'key':key,'value':str(value)})
parts_info={1:('Base vermelha',1),2:('Raposa vermelho',1),3:('Raposa branco',2),4:('Raposa preto',3),5:('Espacador preto',3),6:('Bloquear suporte no encaixe',1)}
for oid,parts,name,extruder,density in [(10,[1],'Base 4 parafusos',1,'30%'),(20,[2,3,4,6],'Cabeca raposa 3 cores',1,'15%'),(30,[5],'Espacador 12 mm',3,'100%')]:
    ob=ET.SubElement(config,'object',{'id':str(oid)})
    for k,v in [('name',name),('extruder',extruder),('sparse_infill_density',density),('enable_support','1' if oid==20 else '0')]:md(ob,k,v)
    if oid==20:md(ob,'support_type','tree(auto)')
    for pid in parts:
        part=ET.SubElement(ob,'part',{'id':str(pid),'subtype':'support_blocker' if pid==6 else 'normal_part'})
        md(part,'name',parts_info[pid][0]);md(part,'extruder',parts_info[pid][1]);md(part,'matrix','1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
        ET.SubElement(part,'mesh_stat',{'face_count':str(len(meshes[pid].find('{'+NS+'}triangles'))),'edges_fixed':'0','degenerate_facets':'0','facets_removed':'0','facets_reversed':'0','backwards_edges':'0'})
plate=ET.SubElement(config,'plate');md(plate,'plater_id',1);md(plate,'plater_name','Raposa Zumo - 3 cores');md(plate,'locked','false')
counts={}
for oid,x,y in placements:
    inst=ET.SubElement(plate,'model_instance');md(inst,'object_id',oid);md(inst,'instance_id',counts.get(oid,0));md(inst,'identify_id',oid*10+counts.get(oid,0));counts[oid]=counts.get(oid,0)+1
project={'filament_colour':colors,'filament_type':['PLA']*3,'filament_diameter':['1.75']*3,'filament_settings_id':['Generic PLA']*3,'filament_ids':['GFL99']*3,
    'filament_is_support':['0']*3,'filament_map':['1','1','1'],'curr_bed_type':'Textured PEI Plate','flush_volumes_matrix':purge,'flush_volumes_vector':['140','140','140','140','140','140'],
    'flush_multiplier':'1','wipe_tower_x':['192'],'wipe_tower_y':['92'],'wipe_tower_rotation_angle':['0'],'enable_prime_tower':'1'}
# Bambu CLI requer campos de máquina completos ainda na importação inicial.
# Usar um projeto local válido como conjunto de valores padrão e sobrescrever
# os perfis, materiais e ajustes desta peça antes da exportação.
with ZipFile('/home/daniel/workspace/vinyl/sink/Sink_X1C_06_PLA.gcode.3mf') as seed:
    full=json.loads(seed.read('Metadata/project_settings.config'))
full.update(json.loads((PROFILES/'P2S_04_machine.json').read_text()))
full.update(json.loads((PROFILES/'P2S_04_process.json').read_text()))
fila=json.loads((PROFILES/'P2S_04_PLA_1.json').read_text())
for key,value in fila.items():
    if key not in ['type','name','from','setting_id','instantiation','description','compatible_printers','include','inherits']:
        full[key]=[value[0]]*3 if isinstance(value,list) and value else value
full.update(project)
for key in ['type','name','from','setting_id','instantiation','description','compatible_printers','include','inherits']:full.pop(key,None)
full.update({'version':'02.09.01.70','printer_technology':'FFF','filament_volume_map':['0','0','0'],
             'different_settings_to_system':['']*5,'inherits_group':['']*5})
project=full
rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/Objects/objetos.model" Id="rel1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
with ZipFile(PREP/'raposa_3cores_Bambu.3mf','w',ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr('3D/_rels/3dmodel.model.rels',rels)
    z.writestr('3D/3dmodel.model',ET.tostring(root,encoding='utf-8',xml_declaration=True))
    z.writestr('3D/Objects/objetos.model',ET.tostring(geo,encoding='utf-8',xml_declaration=True))
    z.writestr('Metadata/model_settings.config',ET.tostring(config,encoding='utf-8',xml_declaration=True))
    z.writestr('Metadata/project_settings.config',json.dumps(project))
print('Preparados quatro perfis e projeto Bambu com 3 filamentos.')
