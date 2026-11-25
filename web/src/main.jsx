import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Bluetooth, Wifi, WifiOff, Mic, Square, Play, RotateCcw, Plus, Pencil, X, Check, Orbit, Settings2, ShieldCheck, ChevronRight, RefreshCw, Keyboard, Delete, Eye, EyeOff, AlertTriangle} from 'lucide-react';
import './style.css';

const BUSY = ['recording', 'transcribing', 'generating', 'sending', 'running'];

function Rocket({active, recording, belt, ready}) {
  return <svg className={`rocket ${active ? 'active' : ''} ${recording ? 'listening' : ''}`} viewBox="0 0 400 400" role="img" aria-label={active ? 'Foguete preparando a missão' : ready ? 'Foguete pronto' : 'Foguete na base'}>
    <circle className="orbit-ring" cx="200" cy="200" r="152" fill="none" stroke="#dedbd0" strokeDasharray="2 12"/>
    <circle cx="200" cy="200" r="115" fill="#f1e7d8"/>
    <g className="stars" fill="#d79a74"><path d="M72 104 l4 11 11 4-11 4-4 11-4-11-11-4 11-4Z"/><path d="M318 263 l4 10 10 4-10 4-4 10-4-10-10-4 10-4Z"/><circle cx="316" cy="100" r="5"/><circle cx="77" cy="282" r="4"/></g>
    <ellipse cx="200" cy="338" rx="67" ry="8" fill="#2d463d" opacity=".08"/>
    <g className="ship">
      <path className="flame" d="M180 271 Q171 307 200 341 Q231 303 219 271Z" fill="#edb960"/>
      <path className="flame inner" d="M190 270 Q182 297 200 313 Q218 293 210 270Z" fill="#fff1b5"/>
      <path d="M168 179 Q126 203 130 262 L170 243Z" fill="#ed866a" stroke="#334a43" strokeWidth="3"/>
      <path d="M232 179 Q274 203 270 262 L230 243Z" fill="#ed866a" stroke="#334a43" strokeWidth="3"/>
      <path d="M163 229 C148 164 162 111 200 70 C238 111 252 164 237 229 L225 271 L175 271Z" fill="#fffdf4" stroke="#334a43" strokeWidth="3"/>
      <path d="M170 110 Q181 88 200 70 Q219 88 230 110Z" fill="#ed866a" stroke="#334a43" strokeWidth="3"/>
      <path d="M172 247 L228 247 L222 273 L178 273Z" fill="#334a43"/>
      <path d="M224 130 Q239 165 229 207" fill="none" stroke="#e9e7db" strokeWidth="6" strokeLinecap="round"/>
      <circle cx="200" cy="166" r="28" fill="#ed866a" stroke="#334a43" strokeWidth="3"/>
      <circle cx="200" cy="166" r="20" fill={ready ? '#96baa1' : '#9ebdb6'} stroke="#334a43" strokeWidth="3"/>
      {ready ? <path d="m190 166 7 7 13-14" stroke="#fffdf4" strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round"/> : <path d="M187 159 Q193 149 204 152" stroke="#fffdf4" strokeWidth="4" fill="none" strokeLinecap="round"/>}
      <path d="M200 220 L200 281" stroke="#334a43" strokeWidth="8" strokeLinecap="round"/>
      {belt && <g stroke="#b8926c" strokeWidth="9"><path d="m164 202 71 35m0-35-71 35"/><rect x="192" y="212" width="16" height="14" rx="2" fill="#fff9df" stroke="#556958" strokeWidth="3"/></g>}
    </g>
  </svg>;
}

function App() {
  const [state,setState] = useState(null), [online,setOnline] = useState(false), [pending,setPending] = useState(false);
  const [modal,setModal] = useState(null), [error,setError] = useState(''), [dismissed,setDismissed] = useState('');
  const [ssid,setSsid] = useState(''), [password,setPassword] = useState(''), [showPassword,setShowPassword] = useState(false);
  const [keyboard,setKeyboard] = useState(null), [caps,setCaps] = useState(false), [belt,setBelt] = useState(false), [cranks,setCranks] = useState(0), [now,setNow] = useState(Date.now());
  const requestBusy = useRef(false);
  const apply = data => {setState(data);setOnline(true);};
  useEffect(() => {
    let cancelled=false,timer,abort;
    async function poll() {
      abort=new AbortController(); const deadline=setTimeout(()=>abort.abort(),4000);
      try {const r=await fetch('/api/status',{signal:abort.signal});if(!r.ok)throw Error();const data=await r.json();if(!cancelled)apply(data);}
      catch{if(!cancelled)setOnline(false);}
      finally{clearTimeout(deadline);if(!cancelled)timer=setTimeout(poll,1000);}
    }
    poll();return()=>{cancelled=true;clearTimeout(timer);abort?.abort();};
  },[]);
  useEffect(()=>{const id=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(id);},[]);
  useEffect(()=>{if(state?.phase==='generating'){setBelt(false);setCranks(0);}},[state?.phase]);
  async function action(path,body={}) {
    if(requestBusy.current)return false;
    requestBusy.current=true;setPending(true);setError('');setDismissed('');
    if(path==='execute')body={...body,execution_id:crypto.randomUUID()};
    const abort=new AbortController(),deadline=setTimeout(()=>abort.abort(),10000);
    try{
      const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-Kiosk-Request':'1'},body:JSON.stringify(body),signal:abort.signal});
      const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Confira os dados.');
      if(data.phase)apply(data);return true;
    }catch(e){setError(e.name==='AbortError'?'Resposta pendente. Aguarde a atualização da tela.':e.message);return false;}
    finally{clearTimeout(deadline);requestBusy.current=false;setPending(false);}
  }
  const phase=state?.phase||'idle',bt=state?.bluetooth||{},wifi=state?.wifi||{};
  const busy=BUSY.includes(phase),waiting=['generating','transcribing'].includes(phase),running=['sending','running'].includes(phase);
  const ready=!!state?.code&&!busy,recording=phase==='recording';
  const disabled=!online||pending,canRun=ready&&bt.connected&&!bt.uncertain&&!disabled;
  const currentNetwork=wifi.networks?.find(n=>n.connected);
  const seconds=Math.min(30,Math.max(0,Math.floor(now/1000-(state?.recording_since||now/1000))));
  const shownError=error||(state?.error!==dismissed?state?.error:'');
  async function speak(modify=false) {
    if(state?.demo){await action('generate',{text:modify?'Pisque o LED amarelo três vezes.':'Pisque o LED amarelo cinco vezes.',modify});return;}
    await action(recording?'record/finish':'record/start',recording?{}:{modify});
  }
  function close(){setModal(null);setKeyboard(null);setPassword('');}
  function typeKey(key){const setter=keyboard==='ssid'?setSsid:setPassword;setter(v=>key==='⌫'?v.slice(0,-1):(v+(key==='espaço'?' ':key)).slice(0,keyboard==='ssid'?32:128));}

  return <div className={`kiosk ${phase}`}>
    <header><div className="brand-icon" aria-label="Speech2Pico"><Orbit size={29}/></div>{state?.demo&&<span className="demo">DEMO</span>}<div className="status-buttons">
      <button className={`status ${online&&bt.connected?'connected':'disconnected'}`} aria-label={`Bluetooth: ${online&&bt.connected?'conectado':'reconectando'}`} onClick={()=>setModal('bluetooth')}><Bluetooth size={24}/><i/></button>
      <button className={`status ${online&&currentNetwork?'connected':'disconnected'}`} aria-label="Wi-Fi" onClick={()=>setModal('wifi')}>{currentNetwork?<Wifi size={24}/>:<WifiOff size={24}/>}<i/></button>
    </div></header>

    <main>
      <div className="scene">
        <Rocket active={waiting||running} recording={recording} ready={ready} belt={belt&&waiting}/>
        {phase==='done'&&<div className="confetti" aria-hidden="true">{Array.from({length:12},(_,i)=><i key={i} style={{'--i':i}}/>)}</div>}
        <div className="scene-controls">
          {waiting?<><button className={`play-control belt ${belt?'fastened':''}`} aria-label={belt?'Cintos apertados':'Apertar cintos'} onClick={()=>setBelt(v=>!v)}><ShieldCheck size={28}/></button><div className="waiting-dots" role="status" aria-label="Aguardando a API"><i/><i/><i/></div><button className="play-control crank" aria-label="Girar manivela" onClick={()=>setCranks(v=>v+1)}><Settings2 size={28} style={{transform:`rotate(${cranks*90}deg)`}}/><span>{cranks||''}</span></button></>:running?<div className="waiting-dots" role="status" aria-label="Executando no Pololu"><i/><i/><i/></div>:<>
            <span className="scene-spacer"/>
            <button className={`mic ${recording?'is-recording':''}`} aria-label={recording?'Finalizar gravação':'Falar novo código'} onClick={()=>speak()} disabled={disabled}>
              {recording?<Square size={27} fill="currentColor"/>:<Mic size={32}/>}<span className="mic-halo"/>
            </button>
            {recording?<button className="cancel-record" aria-label="Cancelar gravação" onClick={()=>action('record/cancel')}><X size={22}/></button>:<span className="scene-spacer"/>}
          </>}
        </div>
        {recording&&<span className="record-time" role="status">{String(seconds).padStart(2,'0')} / 30</span>}
      </div>

      <nav className="actions" aria-label="Comandos da missão">
        <button className="action execute" disabled={!canRun||phase==='done'} onClick={()=>action('execute',{mission_id:state.mission_id})}><Play size={27} fill="currentColor"/><span>Executar</span></button>
        <button className="action" disabled={!canRun||phase!=='done'} onClick={()=>action('execute',{mission_id:state.mission_id})}><RotateCcw size={27}/><span>Repetir</span></button>
        <button className="action" disabled={!ready||disabled} onClick={()=>speak(true)}><Pencil size={25}/><span>Modificar</span></button>
        <button className="action new" disabled={busy||disabled} onClick={async()=>{if(await action('new'))await speak();}}><Plus size={29}/><span>Novo código</span></button>
      </nav>
      {!online&&<div className="offline" role="status" aria-label="Serviço local desconectado"><RefreshCw className="spin" size={18}/></div>}
      {shownError&&<div className="error-toast" role="alert"><AlertTriangle size={20}/><span>{shownError}</span><button aria-label="Fechar aviso" onClick={()=>{setError('');setDismissed(state?.error||'');}}><X size={19}/></button></div>}
    </main>

    {modal&&<div className="backdrop" onClick={close}><section className="panel" role="dialog" aria-modal="true" aria-label={modal==='wifi'?'Wi-Fi':'Bluetooth'} onClick={e=>e.stopPropagation()}>
      <div className="panel-header"><span>{modal==='wifi'?<Wifi size={24}/>:<Bluetooth size={24}/>}</span><h2>{modal==='wifi'?'Wi-Fi':'Bluetooth'}</h2><button aria-label="Fechar painel" onClick={close}><X size={24}/></button></div>
      {modal==='bluetooth'?<><div className={`robot-row ${online&&bt.connected?'ok':''}`}><Bluetooth size={32}/><div><strong>POLOLU</strong><small>{state?.demo?'Simulado':!online?'Offline':bt.phase==='running'?'Executando':bt.connected?'Conectado':'Reconectando…'}</small></div><i className="dot"/></div><div className="bt-detail"><code>{bt.address}</code><span><RefreshCw size={16}/>1 s</span></div>{!bt.connected&&<p className="compact-note">{bt.message}</p>}{bt.phase==='running'&&<p className="compact-note">Receptor ocupado; sem heartbeat ou parada remota.</p>}{bt.uncertain&&<div className="uncertain"><AlertTriangle size={22}/><p>O código pode ter executado. Confira o robô antes de repetir.</p><button className="primary" onClick={()=>action('bluetooth/acknowledge')}>Conferi o robô</button></div>}</>:<>
        <div className="networks">{wifi.networks?.map(n=><button key={n.ssid} className={ssid===n.ssid?'selected':''} onClick={()=>{setSsid(n.ssid);setPassword('');}}><Wifi size={21}/><span>{n.ssid}<small>{n.connected?'Conectada':n.security||'Aberta'}</small></span>{n.connected?<Check size={20}/>:<ChevronRight size={19}/>}</button>)}</div>
        <button className="scan" disabled={wifi.busy||disabled} onClick={()=>action('wifi/scan')}><RefreshCw className={wifi.busy?'spin':''} size={18}/>{wifi.busy?'Aguarde':'Buscar redes'}</button>
        <label>Rede<div className="input-row"><input aria-label="Rede" value={ssid} maxLength={32} onChange={e=>setSsid(e.target.value)}/><button aria-label="Teclado da rede" onClick={()=>setKeyboard('ssid')}><Keyboard size={22}/></button></div></label>
        <label>Senha<div className="input-row"><input aria-label="Senha" type={showPassword?'text':'password'} autoComplete="off" value={password} maxLength={128} onChange={e=>setPassword(e.target.value)}/><button aria-label="Mostrar ou ocultar senha" onClick={()=>setShowPassword(v=>!v)}>{showPassword?<EyeOff size={20}/>:<Eye size={20}/>}</button><button aria-label="Teclado da senha" onClick={()=>setKeyboard('password')}><Keyboard size={22}/></button></div></label>
        <button className="primary" disabled={disabled||wifi.busy||!ssid.trim()||state?.demo} onClick={async()=>{const secret=password;setPassword('');setKeyboard(null);await action('wifi/connect',{ssid,password:secret});}}><Wifi size={21}/>{wifi.busy?'Conectando…':'Conectar'}</button>
        {(wifi.error||error)&&<p className="compact-note warning" role="alert">{wifi.error||error}</p>}
      </>}
    </section></div>}

    {keyboard&&<section className="keyboard" aria-label="Teclado virtual"><div className="keyboard-top"><span>{keyboard==='ssid'?ssid:'•'.repeat(password.length)}</span><button onClick={()=>setKeyboard(null)} aria-label="Concluir teclado"><Check size={23}/></button></div>{['1234567890','qwertyuiop','asdfghjklç','zxcvbnm'].map(row=><div className="key-row" key={row}>{[...row].map(char=><button key={char} onClick={()=>typeKey(caps?char.toUpperCase():char)}>{caps?char.toUpperCase():char}</button>)}</div>)}<div className="key-row symbols">{[..."@#_-.!?/,:;+=*$%&()[]{}<>|\\~^'\"`áéíóúãõêô"].map(char=><button key={char} onClick={()=>typeKey(char)}>{char}</button>)}</div><div className="key-row"><button className={caps?'selected':''} onClick={()=>setCaps(v=>!v)}>⇧</button><button className="space" onClick={()=>typeKey('espaço')}>espaço</button><button aria-label="Apagar caractere" onClick={()=>typeKey('⌫')}><Delete size={21}/></button></div></section>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App/>);
