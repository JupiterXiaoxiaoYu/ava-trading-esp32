from __future__ import annotations

CUSTOMER_PAGE = r'''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ava Device Activation</title>
<style>
:root{--ink:#242116;--muted:#716a56;--paper:#f8efd9;--card:#fff9ea;--line:#d9c599;--forest:#253021;--amber:#cc8530;--clay:#ae543d;--shadow:0 24px 70px rgba(63,47,21,.16)}
*{box-sizing:border-box}html{scrollbar-color:#9b8354 #ead7ad}body{margin:0;min-height:100vh;color:var(--ink);background:radial-gradient(circle at 85% -4%,rgba(204,133,48,.38),transparent 22rem),radial-gradient(circle at 6% 72%,rgba(95,112,68,.28),transparent 26rem),linear-gradient(115deg,#f7eed8,#e9d3a9);font-family:Aptos,"IBM Plex Sans","Segoe UI",sans-serif}button,input{font:inherit}.shell{min-height:100vh;display:grid;grid-template-columns:minmax(0,1fr) 440px;gap:clamp(20px,4vw,58px);padding:clamp(20px,5vw,64px)}.story{display:flex;flex-direction:column;justify-content:space-between;gap:40px}.mark{display:inline-flex;align-items:center;gap:10px;font-weight:950;letter-spacing:.12em;text-transform:uppercase;color:#745327}.dot{width:18px;height:18px;border-radius:50%;background:conic-gradient(from 30deg,var(--forest),var(--amber),var(--forest));box-shadow:0 0 0 6px rgba(204,133,48,.14)}h1{font-family:Georgia,"Times New Roman",serif;font-size:clamp(44px,7vw,96px);line-height:.88;letter-spacing:-.055em;margin:22px 0 18px;max-width:880px}.lead{font-size:clamp(17px,2vw,23px);line-height:1.45;color:#5d5c48;max-width:720px}.steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:900px}.step{border-top:1px solid rgba(70,58,32,.25);padding-top:14px}.step b{display:block;font-family:Georgia,"Times New Roman",serif;font-size:24px}.step span{display:block;color:var(--muted);font-weight:720;line-height:1.45;margin-top:4px}.panel{align-self:center;background:rgba(255,249,234,.88);border:1px solid rgba(88,66,27,.18);border-radius:34px;box-shadow:var(--shadow);padding:22px;backdrop-filter:blur(10px)}.card{border:1px solid var(--line);border-radius:27px;background:linear-gradient(180deg,#fffaf0,#f6e8c9);padding:22px}.card+.card{margin-top:14px}.kicker{color:#8b642c;text-transform:uppercase;font-weight:950;font-size:12px;letter-spacing:.13em}.title{font-family:Georgia,"Times New Roman",serif;font-size:32px;line-height:1;margin:7px 0}.copy{color:var(--muted);font-weight:720;line-height:1.45;margin:0 0 18px}.form{display:grid;gap:11px}.field label{display:block;color:#766749;text-transform:uppercase;font-weight:950;font-size:11px;letter-spacing:.08em;margin:0 0 6px}.field input{width:100%;border:1px solid var(--line);border-radius:16px;background:#fffdf5;padding:12px 13px;color:var(--ink);outline:none}.field input:focus{border-color:var(--forest);box-shadow:0 0 0 4px rgba(95,112,68,.16)}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:4px}.btn{border:0;border-radius:999px;background:var(--forest);color:#fff4d8;padding:12px 16px;font-weight:950;cursor:pointer;text-decoration:none}.btn.secondary{background:transparent;color:var(--forest);border:1px solid var(--line)}.btn:disabled{opacity:.55;cursor:not-allowed}.status{min-height:24px;color:#5b6249;font-weight:820}.status.bad{color:var(--clay)}.wallet{font-family:"Cascadia Mono","SFMono-Regular",monospace;font-size:12px;overflow-wrap:anywhere;background:#fffdf5;border:1px solid var(--line);border-radius:16px;padding:10px}.devices{display:grid;gap:10px}.device{border:1px solid var(--line);border-radius:19px;background:#fffdf5;padding:13px}.device-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.device b{font-family:Georgia,"Times New Roman",serif;font-size:20px}.pill{display:inline-flex;border-radius:999px;padding:4px 8px;background:#e8dcc0;color:#3d3523;font-size:12px;font-weight:950}.pill.ok{background:#dce9c8;color:#2f5224}.meta{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px;color:var(--muted);font-size:13px;font-weight:760}.empty{border:1px dashed var(--line);border-radius:18px;padding:14px;color:var(--muted);font-weight:760}.fine{font-size:12px;color:#82745a;line-height:1.45;margin-top:14px}@media(max-width:860px){.shell{grid-template-columns:1fr;padding:18px}.steps{grid-template-columns:1fr}.panel{align-self:stretch}.row{grid-template-columns:1fr}h1{font-size:clamp(42px,14vw,68px)}}
</style>
<body>
<main class="shell">
  <section class="story">
    <div>
      <div class="mark"><span class="dot"></span>Ava customer portal</div>
      <h1>Activate Ava Hardware</h1>
      <p class="lead">Connect your Solana wallet, sign one login message, then bind the activation code that came with your device.</p>
    </div>
    <div class="steps" aria-label="Activation steps">
      <div class="step"><b>1</b><span>Connect the wallet you want to use for this hardware account.</span></div>
      <div class="step"><b>2</b><span>Sign the Ava login challenge. No transaction is sent.</span></div>
      <div class="step"><b>3</b><span>Enter the activation code and confirm your device appears.</span></div>
    </div>
  </section>
  <aside class="panel">
    <section class="card">
      <div class="kicker">Wallet sign in</div>
      <div class="title">Verify ownership</div>
      <p class="copy">Ava uses Solana wallet signatures for customer login. The signature only proves wallet ownership; it cannot move funds.</p>
      <form id="wallet-login-form" class="form">
        <div class="field"><label>Wallet</label><input name="wallet" id="wallet" placeholder="Connect wallet or paste public key"></div>
        <div class="row">
          <div class="field"><label>Name optional</label><input name="display_name" placeholder="Ava user"></div>
          <div class="field"><label>App</label><input name="app_id" id="app_id" value="ava_box"></div>
        </div>
        <div class="field"><label>Email optional</label><input name="email" type="email" autocomplete="email" placeholder="you@example.com"></div>
        <div class="actions"><button class="btn" type="button" id="connect-wallet">Connect wallet</button><button class="btn secondary" type="submit">Sign in</button><button class="btn secondary" type="button" id="restore-session">Use saved session</button></div>
        <div id="wallet-view" class="wallet">No wallet connected.</div>
        <div id="login-status" class="status"></div>
      </form>
    </section>
    <section class="card">
      <div class="kicker">Activation</div>
      <div class="title">Bind hardware</div>
      <form id="activation-form" class="form">
        <div class="field"><label>Activation code</label><input name="activation_code" id="activation_code" autocomplete="one-time-code" placeholder="AVA-0000-0000" required></div>
        <div class="actions"><button class="btn" type="submit">Activate device</button><button class="btn secondary" type="button" id="refresh-profile">Refresh</button></div>
        <div id="activation-status" class="status"></div>
      </form>
    </section>
    <section class="card">
      <div class="kicker">My devices</div>
      <div class="title">Connected hardware</div>
      <div id="profile-summary" class="copy">Sign in to view your account.</div>
      <div id="device-list" class="devices"><div class="empty">No session yet.</div></div>
      <div class="fine">Device tokens stay on the device. Customer sessions use a separate portal token stored only in this browser.</div>
    </section>
  </aside>
</main>
<script>
const $=s=>document.querySelector(s);const state={token:localStorage.getItem('ava_customer_token')||'',wallet:'',profile:null};
const qs=new URLSearchParams(location.search);if(qs.get('activation_code'))$('#activation_code').value=qs.get('activation_code');if(qs.get('app_id'))$('#app_id').value=qs.get('app_id');
function setStatus(id,msg,bad=false){const el=$(id);el.textContent=msg||'';el.classList.toggle('bad',!!bad)}
async function api(path,opts={}){const headers={...(opts.headers||{})};if(state.token)headers.Authorization='Bearer '+state.token;const res=await fetch(path,{...opts,headers});const text=await res.text();let body={};try{body=text?JSON.parse(text):{}}catch(e){body={ok:false,error:text}}if(!res.ok||body.ok===false)throw new Error(body.error||res.statusText);return body}
function renderProfile(body){state.profile=body;const c=body.customer||{};$('#profile-summary').textContent=c.wallet?`${c.display_name||'Wallet user'} - ${short(c.wallet)}`:(c.email?`${c.display_name||c.email} - ${c.email}`:'Sign in to view your account.');const devices=body.devices||[];$('#device-list').innerHTML=devices.length?devices.map(d=>`<div class="device"><div class="device-head"><b>${esc(d.name||d.device_id)}</b><span class="pill ${['active','online_seen'].includes(d.status)?'ok':''}">${esc(d.status||'unknown')}</span></div><div class="meta"><span>ID ${esc(d.device_id||'-')}</span><span>App ${esc(d.app_id||'-')}</span><span>Board ${esc(d.board_model||'-')}</span><span>Firmware ${esc(d.firmware_version||'-')}</span></div></div>`).join(''):'<div class="empty">No device bound yet. Enter your activation code above.</div>'}
function esc(v){return String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}function short(v){v=String(v||'');return v.length>12?v.slice(0,4)+'...'+v.slice(-4):v}
async function me(){const body=await api('/customer/me');renderProfile(body);return body}
function bytesToBase58(bytes){const alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';let digits=[0];for(const byte of bytes){let carry=byte;for(let j=0;j<digits.length;j++){carry+=digits[j]<<8;digits[j]=carry%58;carry=(carry/58)|0}while(carry){digits.push(carry%58);carry=(carry/58)|0}}let out='';for(const byte of bytes){if(byte===0)out+='1';else break}for(let q=digits.length-1;q>=0;q--)out+=alphabet[digits[q]];return out}
async function connectWallet(){const provider=window.solana;if(!provider||!provider.isPhantom){setStatus('#login-status','No Solana wallet found. Paste a public key or install Phantom.',true);return ''}const resp=await provider.connect();state.wallet=resp.publicKey.toString();$('#wallet').value=state.wallet;$('#wallet-view').textContent=state.wallet;return state.wallet}
$('#connect-wallet').addEventListener('click',async()=>{try{await connectWallet();setStatus('#login-status','Wallet connected. Sign in next.')}catch(err){setStatus('#login-status',err.message,true)}});
$('#wallet-login-form').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);let wallet=String(fd.get('wallet')||state.wallet||'').trim();try{if(!wallet)wallet=await connectWallet();if(!wallet)throw new Error('wallet_required');const app_id=String(fd.get('app_id')||'ava_box');const challenge=await api('/customer/wallet/challenge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet,app_id})});let signature='';const provider=window.solana;if(provider&&provider.publicKey&&provider.publicKey.toString()===wallet&&provider.signMessage){const encoded=new TextEncoder().encode(challenge.message);const signed=await provider.signMessage(encoded,'utf8');signature=bytesToBase58(signed.signature)}else{signature=prompt('Paste wallet signature for this message:\n\n'+challenge.message)||''}const result=await api('/customer/wallet/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet,signature,nonce:challenge.nonce,app_id,email:fd.get('email')||'',display_name:fd.get('display_name')||''})});state.token=result.customer_token;localStorage.setItem('ava_customer_token',state.token);renderProfile(result);setStatus('#login-status','Wallet verified. You can activate hardware now.')}catch(err){setStatus('#login-status',err.message,true)}});
$('#activation-form').addEventListener('submit',async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));try{const result=await api('/customer/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});renderProfile(result);setStatus('#activation-status','Device activated and bound to this wallet.');e.target.reset()}catch(err){setStatus('#activation-status',err.message,true)}});
$('#restore-session').addEventListener('click',async()=>{if(!state.token){setStatus('#login-status','No saved session in this browser.',true);return}try{await me();setStatus('#login-status','Session restored.')}catch(err){setStatus('#login-status','Saved session is invalid. Sign in again.',true)}});
$('#refresh-profile').addEventListener('click',async()=>{try{await me();setStatus('#activation-status','Profile refreshed.')}catch(err){setStatus('#activation-status','Sign in first.',true)}});
if(state.token)me().catch(()=>{});
</script>
</html>'''
