let S={messages:[],workflows:[],current:null,genBuild:null,onlyPub:true,user:null,sid:null,followTimer:null};
const $=id=>document.getElementById(id);
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}
function esc(t){return String(t??'').replace(/&/g,'&amp;').replace(/</g,'&lt;')}

async function boot(){const d=await api('/api/bootstrap');
  if(!d.configured||!d.connected){
    $('login').classList.add('show');$('shell').classList.remove('show');
    setTimeout(()=>{($('lg-server').value?$('lg-name'):$('lg-server')).focus()},50);
    if(d.server)$('lg-server').value=d.server;
    S.profiles=d.profiles||[];const row=$('lg-prof-row');
    if(S.profiles.length){row.style.display='block';
      $('lg-prof').innerHTML='<option value="">手动填写…</option>'+S.profiles.map(p=>
        '<option value="'+esc(p.name)+'"'+(p.name===d.profile?' selected':'')+'>'+esc(p.name)+' — '+esc(p.server)+(p.user?'（'+esc(p.user)+'）':'')+'</option>').join('');
      if(d.profile&&S.profiles.some(p=>p.name===d.profile))PROF=d.profile}
    else row.style.display='none';
    if(d.configured&&!d.connected)$('lg-err').textContent='连不上远端：'+(d.detail||'');
    return}
  $('login').classList.remove('show');$('shell').classList.add('show');
  S.user=d.user;S.workflows=d.workflows;
  $('u-name').textContent=d.user.name;$('u-role').textContent=d.user.role==='admin'?'管理员':'成员';
  $('u-dot').textContent=(d.user.name||'?').slice(0,1);
  $('conn-note').textContent='已连接 '+d.server+(d.profile?'（档案 '+d.profile+'）':'');
  renderList();watchFailures();setTimeout(()=>{const el=$('chat-input');el&&el.focus()},50)}
let FAILSEEN=null;
function watchFailures(){if(S._fw)return;S._fw=setInterval(checkFailures,90000);checkFailures()}
async function checkFailures(){if(!S.user)return;
  try{const d=await api('/api/overview');const fails=d.recent_failures||[];
    if(FAILSEEN===null){FAILSEEN=new Set(fails.map(f=>f.run_id));return}
    const fresh=fails.filter(f=>!FAILSEEN.has(f.run_id));
    if(!fresh.length)return;
    fails.forEach(f=>FAILSEEN.add(f.run_id));
    $('nav-ov').classList.add('dot');
    try{if(Notification.permission==='default')Notification.requestPermission();
      if(Notification.permission==='granted'){const f=fresh[0];
        new Notification('工作流失败：'+(f.workflow||''),
          {body:String(f.error||'').slice(0,120)+(fresh.length>1?'（等 '+fresh.length+' 条）':'')})}}
    catch(e){}}
  catch(e){}}
let REG=false,PROF='';
async function pickProfile(){const v=$('lg-prof').value;PROF=v;$('lg-err').textContent='';
  const p=(S.profiles||[]).find(x=>x.name===v);
  if(p){$('lg-server').value=p.server||'';if(p.user)$('lg-name').value=p.user}
  if(!v)return;
  try{await api('/api/config',{mode:'use',profile:v});await boot()}
  catch(e){$('lg-err').textContent='档案「'+v+'」'+e.message;$('lg-pass').focus()}}
function toggleMode(){REG=!REG;$('lg-reg-row').style.display=REG?'block':'none';
  $('lg-go').textContent=REG?'注册并登录':'登录';
  $('lg-switch').textContent=REG?'已有账号？直接登录':'没有账号？注册（首个注册者自动成为管理员）'}
async function saveConfig(){$('lg-err').textContent='';
  try{await api('/api/config',{server:$('lg-server').value.trim(),mode:REG?'register':'login',
    name:$('lg-name').value.trim(),password:$('lg-pass').value,profile:PROF||'',
    register_token:$('lg-reg')?$('lg-reg').value:''});
    await boot()}catch(e){$('lg-err').textContent=(REG?'注册':'登录')+'失败：'+e.message}}
function show(v){$('view-chat').classList.toggle('act',v==='chat');
  $('view-wf').classList.toggle('act',v==='wf');
  $('view-ov').style.display=v==='ov'?'block':'none';
  $('nav-chat').classList.toggle('act',v==='chat');
  $('nav-wf').classList.toggle('act',v==='wf');
  $('nav-ov').classList.toggle('act',v==='ov');
  if(v==='wf')boot();if(v==='ov'){$('nav-ov').classList.remove('dot');loadOverview()}}
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

function nearBottom(){const el=$('chat-scroll');return el.scrollHeight-el.scrollTop-el.clientHeight<140}
function renderChat(waiting){const stick=nearBottom();$('chat-col').innerHTML=S.messages.map((m,i)=>{
    if(m.kind==='action')return `<div style="margin:-8px 0 12px 42px;font:11.5px/1.5 ui-monospace,monospace;color:var(--faint)">⚙ ${esc(m.text)}</div>`;
    if(m.kind==='build')return `<div style="margin:0 0 14px 42px;border-left:3px solid var(--accent-line);padding:6px 12px;font:12px/1.7 ui-monospace,monospace;color:var(--sub);white-space:pre-wrap">${esc(m.text)}</div>`;
    if(m.kind==='answerbox')return `<div style="margin:0 0 14px 42px;display:flex;gap:8px;max-width:520px">
      <input id="ab-input" placeholder="回答莉莉丝…" style="flex:1;border:1px solid var(--accent);border-radius:9px;padding:8px 11px"
        onkeydown="if(event.key==='Enter')sendAnswer('${m.build_id}')">
      <button class="primary" onclick="sendAnswer('${m.build_id}')">转交</button></div>`;
    const last=waiting&&i===S.messages.length-1;
    const body=m.role==='user'?esc(m.text):md(m.text);
    return `<div class="msg ${m.role==='user'?'user':'bot'}">
    <div class="av">${m.role==='user'?'我':'远'}</div>
    <div class="bd${last?' wait':''}">${body}${last?'<i>…</i>':''}</div></div>`}).join('');
  if(stick)$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight}

/* ── 迷你 markdown（切片5）：先转义后变换，支持表格/代码块/列表/加粗/行内码 ── */
function md(t){
  t=esc(t);
  t=t.replace(/```[a-z]*\n([\s\S]*?)```/g,(_,c)=>`<pre class="md-pre">${c}</pre>`);
  const lines=t.split('\n');const out=[];let i=0;
  while(i<lines.length){
    const L=lines[i];
    if(/^\|.*\|\s*$/.test(L)&&i+1<lines.length&&/^\|[\s:|-]+\|\s*$/.test(lines[i+1])){
      const head=L.split('|').slice(1,-1).map(x=>x.trim());
      i+=2;const rows=[];
      while(i<lines.length&&/^\|.*\|\s*$/.test(lines[i])){
        rows.push(lines[i].split('|').slice(1,-1).map(x=>x.trim()));i++}
      out.push('<table class="md-t"><tr>'+head.map(h=>`<th>${inl(h)}</th>`).join('')+'</tr>'
        +rows.map(r=>'<tr>'+r.map(c=>`<td>${inl(c)}</td>`).join('')+'</tr>').join('')+'</table>');
      continue}
    if(/^[-*] /.test(L)){
      const items=[];
      while(i<lines.length&&/^[-*] /.test(lines[i])){items.push(lines[i].slice(2));i++}
      out.push('<ul class="md-ul">'+items.map(x=>`<li>${inl(x)}</li>`).join('')+'</ul>');
      continue}
    if(/^#{1,3} /.test(L)){out.push(`<div class="md-h">${inl(L.replace(/^#+ /,''))}</div>`);i++;continue}
    out.push(L?`<p class="md-p">${inl(L)}</p>`:'');i++}
  return out.join('')}
function inl(t){return t
  .replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')
  .replace(/`([^`]+)`/g,'<code class="md-c">$1</code>')}

function pushMsg(role,text,wait){S.messages.push({role,text});renderChat(wait)}
async function send(){const t=$('chat-input').value.trim();if(!t||S.sending)return;
  S.sending=true;$('send-btn').disabled=true;$('chat-input').value='';
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
          S.messages.push({role:'assistant',kind:'action',text:`${ev.tool} → ${ev.summary||''}`,
            tool:ev.tool,build_id:ev.build_id});
          S.messages.push(bubble);renderChat(true)}
        else if(ev.type==='final'){cur().text=ev.text||cur().text||'(空回复)';sawFinal=true}
        else if(ev.type==='error'){throw new Error(ev.text)}
      }}
    if(!cur().text&&!sawFinal)cur().text='(空回复)';
    renderChat(false);saveSession();
    const gen=[...S.messages].reverse().find(m=>m.kind==='action'&&m.tool==='generate_workflow'&&m.build_id);
    if(gen)followBuild(gen.build_id)}
  catch(e){
    try{const r=await api('/api/chat',{messages:historyForSend});
      cur().text=r.text||'(空回复)';renderChat(false)}
    catch(e2){cur().text='远端出错：'+e2.message;renderChat(false)}}
  S.sending=false;$('send-btn').disabled=false;const ci=$('chat-input');ci&&ci.focus()}

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
    <div id="run-result"></div>
    <div id="run-history"></div></div>`;
  loadHistory(id);
  $('wf-detail').scrollIntoView({behavior:'smooth',block:'nearest'})}
async function loadHistory(id){const box=$('run-history');if(!box)return;
  try{const runs=await api('/api/workflow/history/'+id);
    if(!runs.length){box.innerHTML='<div class="empty" style="padding:6px 0">还没跑过</div>';return}
    box.innerHTML='<h4 class="h-title">最近运行（点行看过程）</h4>'+runs.map(r=>{
      const st=r.status==='succeeded'?'ok':(r.status==='failed'?'bad':'');
      const mk=r.status==='succeeded'?'✓':(r.status==='failed'?'✕':'…');
      return '<div class="h-item"><div class="h-row '+st+'" onclick="toggleEvents(\''+r.id+'\',this)">'+
        '<span class="h-st">'+mk+'</span>'+
        '<span class="h-at">'+esc(r.at)+'</span>'+
        '<span class="h-tx">'+esc(r.error||r.brief||'')+'</span></div>'+
        '<div class="h-ev" id="ev-'+r.id+'"></div></div>'}).join('')}
  catch(e){box.innerHTML=''}}
async function toggleEvents(id,row){const box=$('ev-'+id);if(!box)return;
  if(box.classList.contains('open')){box.classList.remove('open');return}
  box.classList.add('open');
  if(!box.dataset.loaded){box.innerHTML='<div class="ev-row"><span class="ev-tx">加载中…</span></div>';
    try{const evs=await api('/api/workflow/runevents/'+id);box.dataset.loaded='1';
      box.innerHTML=evs.length?evs.map(e=>{
        const bad=/failed|error/.test(e.type)||/失败|error/i.test(e.extra||'');
        return '<div class="ev-row'+(bad?' bad':'')+'">'+
          '<span class="ev-at">'+esc(e.at)+'</span>'+
          '<span class="ev-ty">'+esc(e.type)+'</span>'+
          '<span class="ev-tx">'+esc(e.label)+(e.extra?' · '+esc(e.extra):'')+'</span></div>'}).join('')
        :'<div class="ev-row"><span class="ev-tx">没有事件记录</span></div>'}
    catch(e){box.innerHTML='<div class="ev-row bad"><span class="ev-tx">'+esc(e.message)+'</span></div>';delete box.dataset.loaded}}}
async function runWf(btn){btn.disabled=true;const inputs={};
  document.querySelectorAll('#run-form [data-k]').forEach(el=>{
    try{inputs[el.dataset.k]=el.dataset.json?JSON.parse(el.value):el.value}catch(e){}});
  const box=$('run-result');box.innerHTML='<div class="result r-ok">远端运行中…</div>';
  try{const r=await api('/api/workflow/run',{app_id:S.current.id,inputs});
    const rows=Object.entries(r.outputs||{}).map(([k,v])=>`<div class="kv"><b>${esc(k)}</b><span>${esc(typeof v==='object'?JSON.stringify(v,null,2):v)}</span></div>`).join('');
    box.innerHTML=r.status==='succeeded'?`<div class="result r-ok">${rows||'(无输出)'}</div>`
      :`<div class="result r-err">状态 ${esc(r.status)}${r.error?'：'+esc(r.error):''}</div>`}
  catch(e){box.innerHTML=`<div class="result r-err">${esc(e.message)}</div>`}
  btn.disabled=false;if(S.current)loadHistory(S.current.id)}
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

/* ── 会话持久化（切片4）：与 CLI 共享 ~/.guanjia/sessions/ ── */
async function initSessions(){
  try{
    const list=await api('/api/sessions');
    if(!S.sid)S.sid=list.length?list[0].id:Math.random().toString(16).slice(2,10);
    const pick=$('sess-pick');
    pick.innerHTML=list.map(x=>`<option value="${x.id}">${esc(x.title||x.id)} · ${esc(x.updated_at)}</option>`).join('')
      +(list.some(x=>x.id===S.sid)?'':`<option value="${S.sid}">新对话</option>`);
    pick.value=S.sid;
    if(list.some(x=>x.id===S.sid)){
      const data=await api('/api/sessions/'+S.sid);
      if(data&&data.messages){S.messages=data.messages;renderChat(false)}}}
  catch(e){}}
function saveSession(){if(S.sid)api('/api/sessions/save',{id:S.sid,messages:S.messages}).then(initSessions).catch(()=>{})}
async function switchSession(sid){S.sid=sid;
  const data=await api('/api/sessions/'+sid).catch(()=>null);
  S.messages=(data&&data.messages)||[];renderChat(false)}
function newSession(){S.sid=Math.random().toString(16).slice(2,10);S.messages=[];renderChat(false);initSessions()}
initSessions();


/* ── 对话内构建跟踪（切片3）：进度卡 + 提问答框 ── */
async function followBuild(buildId){
  if(S.followTimer)clearInterval(S.followTimer);
  S.messages.push({role:'assistant',kind:'build',build_id:buildId,text:'跟踪构建 '+buildId.slice(0,8)+' …'});
  const card=S.messages[S.messages.length-1];renderChat(false);
  S.followTimer=setInterval(async()=>{
    try{
      const st=await api('/api/workflow/build/'+buildId);
      let line=`${st.status} · 修订 ${st.revision??0}`;
      if(st.narration)line+='\n'+st.narration.slice(0,80);
      card.text='构建 '+buildId.slice(0,8)+'\n'+line;
      if(['published','ready','needs_attention','failed','cancelled'].includes(st.status)){
        clearInterval(S.followTimer);S.followTimer=null;
        if(st.published_version){
          S.messages.push({role:'assistant',text:`搭好了！已发布 v${st.published_version}——直接说「跑一下」就能用。`});
          boot()}
        else if(st.pending_question){
          S.messages.push({role:'assistant',text:'莉莉丝在等你回答：'+st.pending_question});
          S.messages.push({role:'assistant',kind:'answerbox',build_id:buildId})}
        else{
          S.messages.push({role:'assistant',text:`构建结束（${st.status}${st.error?'：'+st.error:''}）——说「继续刚才的构建」可续跑。`})}
      }
      renderChat(false);
      if(!S.followTimer)saveSession()}
    catch(e){}
  },4000)}
async function sendAnswer(buildId){
  const el=document.getElementById('ab-input');const text=(el&&el.value.trim())||'';
  if(!text)return;
  S.messages=S.messages.filter(m=>m.kind!=='answerbox');
  S.messages.push({role:'user',text});renderChat(false);
  try{await api('/api/workflow/answer',{build_id:buildId,message:text});
    S.messages.push({role:'assistant',text:'已转交，继续跟踪。'});followBuild(buildId)}
  catch(e){S.messages.push({role:'assistant',text:'转交失败：'+e.message});renderChat(false)}}
