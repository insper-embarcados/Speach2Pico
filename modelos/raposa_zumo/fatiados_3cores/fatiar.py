from pathlib import Path
import subprocess, sys, json
root=Path(__file__).resolve().parent
mode=sys.argv[1]
if mode not in {'prepare', 'slice'}:
    raise SystemExit('Modo esperado: prepare ou slice')
for tag in sys.argv[2:]:
    if tag not in {'P2S_04', 'P2S_06', 'X1C_04', 'X1C_06'}:
        raise SystemExit(f'Perfil desconhecido: {tag}')
    out=root/tag
    args=['flatpak','run','--command=bambu-studio','com.bambulab.BambuStudio','--datadir',str(root/'preparacao'/('runtime_'+tag)),
          '--debug','3','--load-settings',';'.join(str(root/'preparacao/perfis'/f'{tag}_{kind}.json') for kind in ['machine','process']),
          '--load-filaments',';'.join(str(root/'preparacao/perfis'/f'{tag}_PLA_{i}.json') for i in [1,2,3]),
          # A CLI deduz um único material quando os três presets têm o mesmo
          # nome. As cores explícitas preservam a torre nas trocas de PLA.
          '--filament-colour','#CA1536;#F4EFE5;#24252C',
          '--allow-multicolor-oneplate',
          '--arrange','0','--orient','0','--outputdir',str(out),'--export-3mf',f'Raposa_Zumo_{tag}_3cores'+('.gcode.3mf' if mode=='slice' else '.3mf')]
    if mode=='slice':args+=['--slice','0','--mstpp','900']
    args+=[str(root/'preparacao/raposa_3cores_Bambu.3mf')]
    log=out/('fatiamento.log' if mode=='slice' else 'importacao.log')
    with log.open('w') as f:
        done=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT)
    print(json.dumps({'tag':tag,'mode':mode,'returncode':done.returncode,'log':str(log)}),flush=True)
    if done.returncode!=0:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-15:]),flush=True)
        sys.exit(1)
