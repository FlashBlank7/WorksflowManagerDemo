let S={messages:[],workflows:[],current:null,genBuild:null,onlyPub:true,user:null};
const $=id=>document.getElementById(id);
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}
function esc(t){return String(t??'').replace(/&/g,'&amp;').replace(/</g,'&lt;')}

async function boot(){const d=await api('/api/bootstrap');
  if(!d.configured||!d.connected){
    $('login').classList.add('show');$('shell').classList.remove('show');
    if(d.server)$('lg-server').value=d.server;
    if(d.configured&&!d.connected)$('lg-err').textContent='连不上远端：'+(d.detail||'');
    return}
  $('login').classList.remove('show');$('shell').classList.add('show');
  S.user=d.user;S.workflows=d.workflows;
  $('u-name').textContent=d.user.name;$('u-role').textContent=d.user.role==='admin'?'管理员':'成员';
  $('u-dot').textContent=(d.user.name||'?').slice(0,1);
  $('conn-note').textContent='已连接 '+d.server;
  renderList()}
let REG=false;
function toggleMode(){REG=!REG;$('lg-reg-row').style.display=REG?'block':'none';
  $('lg-go').textContent=REG?'注册并登录':'登录';
  $('lg-switch').textContent=REG?'已有账号？直接登录':'没有账号？注册（首个注册者自动成为管理员）'}
async function saveConfig(){$('lg-err').textContent='';
  try{await api('/api/config',{server:$('lg-server').value.trim(),mode:REG?'register':'login',
    name:$('lg-name').value.trim(),password:$('lg-pass').value,
    register_token:$('lg-reg')?$('lg-reg').value:''});
    await boot()}catch(e){$('lg-err').textContent=(REG?'注册':'登录')+'失败：'+e.message}}
function show(v){$('view-chat').classList.toggle('act',v==='chat');
  $('view-wf').classList.toggle('act',v==='wf');
  $('view-ov').style.display=v==='ov'?'block':'none';
  $('nav-chat').classList.toggle('act',v==='chat');
  $('nav-wf').classList.toggle('act',v==='wf');
  $('nav-ov').classList.toggle('act',v==='ov');
  if(v==='wf')boot();if(v==='ov')loadOverview()}
async function loadOverview(){try{const d=await api('/api/overview');
  const rt=d.runs_today;
  $('ov-stats').innerHTML=`
    <div class="stat"><div class="num">${rt.total}</div><div class="lbl">今日运行</div></div>
    <div class="stat good"><div class="num">${rt.succeeded}</div><div class="lbl">成功</div></div>
    <div class="stat ${rt.failed?'bad':''}"><div class="num">${rt.failed}</div><div class="lbl">失败</div></div>
    <div class="stat"><div class="num">${d.published_workflows}</div><div class="lbl">已发布工作流</div></div>
    <div class="stat"><div class="num">${d.builds_active}</div><div class="lbl">生成中</div></div>`;
  $('ov-schedules').innerHTML=d.schedules.map(s=>`<div class="line-item"><b>${esc(s.workflow)}</b>
    <span class="sub2">每天 ${s.at}（${esc(s.timezone)}）</span>
    <span class="right">${s.last_fire_date?'最近触发 '+esc(s.last_fire_date):'尚未触发'}</span></div>`).join('')
    ||'<div class="line-item sub2">还没有定时任务——在生成需求里写"每天X点自动运行"即可</div>';
  $('ov-failures').innerHTML=d.recent_failures.map(f=>`<div class="line-item"><b>${esc(f.workflow)}</b>
    <span class="sub2">${esc(f.error||'').slice(0,60)}</span>
    <span class="right">run ${esc(f.run_id)} · ${esc(f.at)}</span></div>`).join('')
    ||'<div class="line-item sub2">近期没有失败 🎉</div>'}
  catch(e){$('ov-stats').innerHTML='<div class="stat bad"><div class="num">!</div><div class="lbl">'+esc(e.message)+'</div></div>'}}

function renderChat(waiting){$('chat-col').innerHTML=S.messages.map((m,i)=>{
    if(m.kind==='action')return `<div style="margin:-8px 0 12px 42px;font:11.5px/1.5 ui-monospace,monospace;color:var(--faint)">⚙ ${esc(m.text)}</div>`;
    const last=waiting&&i===S.messages.length-1;
    return `<div class="msg ${m.role==='user'?'user':'bot'}">
    <div class="av">${m.role==='user'?'我':'远'}</div>
    <div class="bd${last?' wait':''}">${esc(m.text)}${last?'<i>…</i>':''}</div></div>`}).join('');
  $('chat-scroll').scrollTop=$('chat-scroll').scrollHeight}
function pushMsg(role,text,wait){S.messages.push({role,text});renderChat(wait)}
async function send(){const t=$('chat-input').value.trim();if(!t)return;$('chat-input').value='';
  pushMsg('user',t);
  const historyForSend=S.messages.filter(m=>!m.kind&&m.text);
  pushMsg('assistant','',true);
  const cur=()=>S.messages[S.messages.length-1];
  try{
    const resp=await fetch('/api/chat/stream',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:historyForSend})});
    if(!resp.ok)throw new Error('HTTP '+resp.status);
    const reader=resp.body.getReader();const dec=new TextDecoder();let buf='';let sawFinal=false;
    for(;;){const {done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      let idx;
      while((idx=buf.indexOf('\n\n'))>=0){
        const line=buf.slice(0,idx).trim();buf=buf.slice(idx+2);
        if(!line.startsWith('data: '))continue;
        const ev=JSON.parse(line.slice(6));
        if(ev.type==='delta'&&ev.text){cur().text+=ev.text;renderChat(true)}
        else if(ev.type==='action'){
          const bubble=S.messages.pop();
          S.messages.push({role:'assistant',kind:'action',text:`${ev.tool} → ${ev.summary||''}`});
          S.messages.push(bubble);renderChat(true)}
        else if(ev.type==='final'){cur().text=ev.text||cur().text||'(空回复)';sawFinal=true}
        else if(ev.type==='error'){throw new Error(ev.text)}
      }}
    if(!cur().text&&!sawFinal)cur().text='(空回复)';
    renderChat(false)}
  catch(e){
    try{const r=await api('/api/chat',{messages:historyForSend});
      cur().text=r.text||'(空回复)';renderChat(false)}
    catch(e2){cur().text='远端出错：'+e2.message;renderChat(false)}}}

function togglePub(){S.onlyPub=!S.onlyPub;$('wf-pub').classList.toggle('on',S.onlyPub);renderList()}
function renderList(){const q=($('wf-search').value||'').toLowerCase();
  const list=S.workflows.filter(w=>(!S.onlyPub||w.published)&&(!q||(w.name+w.description).toLowerCase().includes(q)));
  $('wf-count').textContent=list.length+' 个';
  $('wf-list').innerHTML=list.map(w=>`
    <div class="wf-card ${S.current&&S.current.id===w.id?'sel':''}" onclick="openWf('${w.id}')">
      <h4>${esc(w.name)}</h4><div class="desc">${esc(w.description)}</div>
      <span class="badge ${w.published?'b-on':'b-off'}">${w.published?'v'+w.version+' 已发布':'未发布'}</span>
    </div>`).join('')||'<div class="empty">没有匹配的工作流</div>'}
async function openWf(id){S.current=S.workflows.find(w=>w.id===id);renderList();
  let schema=[];try{schema=await api('/api/workflow/inputs/'+id)}catch(e){}
  const fields=schema.map(f=>{const isObj=typeof f.example==='object';
    return `<div class="field"><label>${esc(f.label)}<code>${f.name} · ${f.type}</code></label>
    ${isObj?`<textarea data-k="${f.name}" data-json="1">${esc(JSON.stringify(f.example,null,2))}</textarea>`
          :`<input data-k="${f.name}" value="${esc(f.example)}">`}</div>`}).join('');
  $('wf-detail').innerHTML=`<div class="detail"><h3>${esc(S.current.name)}
    <span class="badge ${S.current.published?'b-on':'b-off'}">${S.current.published?'v'+S.current.version:'未发布'}</span></h3>
    <div class="meta">${esc(S.current.description)}</div>
    <div id="run-form">${fields||'<div class="empty" style="padding:8px 0">无输入声明，直接运行</div>'}</div>
    <div class="run-row"><button class="primary" ${S.current.published?'':'disabled'} onclick="runWf(this)">运行</button>
    <span class="note">执行发生在远端，本地只接收结果</span></div>
    <div id="run-result"></div></div>`;
  $('wf-detail').scrollIntoView({behavior:'smooth',block:'nearest'})}
async function runWf(btn){btn.disabled=true;const inputs={};
  document.querySelectorAll('#run-form [data-k]').forEach(el=>{
    try{inputs[el.dataset.k]=el.dataset.json?JSON.parse(el.value):el.value}catch(e){}});
  const box=$('run-result');box.innerHTML='<div class="result r-ok">远端运行中…</div>';
  try{const r=await api('/api/workflow/run',{app_id:S.current.id,inputs});
    const rows=Object.entries(r.outputs||{}).map(([k,v])=>`<div class="kv"><b>${esc(k)}</b><span>${esc(typeof v==='object'?JSON.stringify(v,null,2):v)}</span></div>`).join('');
    box.innerHTML=r.status==='succeeded'?`<div class="result r-ok">${rows||'(无输出)'}</div>`
      :`<div class="result r-err">状态 ${esc(r.status)}${r.error?'：'+esc(r.error):''}</div>`}
  catch(e){box.innerHTML=`<div class="result r-err">${esc(e.message)}</div>`}
  btn.disabled=false}
async function generate(){const req=$('gen-req').value.trim();
  if(req.length<10){alert('需求至少 10 个字');return}
  $('gen-btn').disabled=true;const p=$('gen-progress');p.classList.add('show');p.textContent='已提交远端，莉莉丝开工…';
  try{const r=await api('/api/workflow/generate',{requirement:req,
    thinking_enabled:$('gen-think').checked,effort:$('gen-effort').value});
    S.genBuild=r.build_id;pollGen()}
  catch(e){p.textContent='提交失败：'+e.message;$('gen-btn').disabled=false}}
async function pollGen(){if(!S.genBuild)return;
  try{const s=await api('/api/workflow/build/'+S.genBuild);
    $('gen-progress').textContent=`状态 ${s.status} · 草稿修订 ${s.revision??0}`+
      (s.published_version?` · 已发布 v${s.published_version}`:'')+
      (s.pending_question?`\n莉莉丝提问：${s.pending_question}`:'')+
      (s.narration?`\n${s.narration}`:'')+(s.error?`\n${s.error}`:'');
    if(['published','ready','needs_attention','failed','cancelled'].includes(s.status)){
      $('gen-btn').disabled=false;boot();return}}catch(e){}
  setTimeout(pollGen,4000)}
boot();
