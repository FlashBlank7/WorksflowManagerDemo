let S={messages:[],workflows:[],current:null,genBuild:null,onlyPub:true,user:null,sid:null,followTimer:null};
const $=id=>document.getElementById(id);
// 运行状态的中文说法。状态码是给机器看的——
// 2026-08-29 之前结果框里直接印「状态 failed」。
// 服务端同一天把状态码从各条出口都堵掉了，CLI 那边也改了，这里漏着。
const RUN_WORDS={succeeded:'跑成了',failed:'没跑成',cancelled:'取消了',
  paused:'停下等人填',running:'还在跑',queued:'排队中'};

async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d}
function esc(t){return String(t??'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
// 与 CLI 的 workflow.coerce_input 同一套规则；改一边记得同步另一边
function coerceInput(raw,type){const k=String(type||'string').toLowerCase();
  if(k==='array'||k==='object'||k==='any'||k==='json')return JSON.parse(raw);
  if(k==='number'||k==='float'){const n=Number(raw);if(raw.trim()===''||Number.isNaN(n))throw new Error('要填数字');return n}
  // 整数这一支原来是 Number(raw)+isInteger：**空串会变成 0**，
  // 而下面「少了必填项就别发」是拿 String(值).trim()==='' 判的，
  // 0 不是空串，于是必填校验放行、静默发出一个 0。
  // 同一支还把 '3.0'、'1e3'、'0x10' 当整数收下，而 Python 那边
  // int() 全都拒——两边规则说好是一套的（见 coerce_input 的注释）。
  if(k==='integer'||k==='int'){const s=raw.trim();
    if(!/^[+-]?\d+(_\d+)*$/.test(s))throw new Error('要填整数');
    return Number(s.replace(/_/g,''))}
  if(k==='boolean'||k==='bool')return ['true','1','yes','y','是','on'].includes(raw.trim().toLowerCase());
  return raw}
function needsTextarea(f){const k=String(f.type||'string').toLowerCase();
  return k==='array'||k==='object'||k==='any'||k==='json'
    ||(typeof f.example==='string'&&f.example.includes('\n'))}

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
  S.server=d.server;
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
  $('lg-profname').style.display=v?'none':'block';
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
    name:$('lg-name').value.trim(),password:$('lg-pass').value,
    profile:PROF||($('lg-profname').value.trim()||''),
    register_token:$('lg-reg')?$('lg-reg').value:''});
    await boot()}catch(e){$('lg-err').textContent=(REG?'注册':'登录')+'失败：'+e.message}}
function show(v){$('view-chat').classList.toggle('act',v==='chat');
  $('view-wf').classList.toggle('act',v==='wf');
  $('view-ov').style.display=v==='ov'?'block':'none';
  $('nav-chat').classList.toggle('act',v==='chat');
  $('nav-wf').classList.toggle('act',v==='wf');
  $('nav-ov').classList.toggle('act',v==='ov');
  if(v==='wf')boot();if(v==='ov'){$('nav-ov').classList.remove('dot');loadOverview()}}
function gotoWf(id){  // 从统筹页跳到工作流详情：先切视图，找不到就只切页
  if(!(S.workflows||[]).some(w=>w.id===id)){show('wf');return}
  show('wf');openWf(id)}
async function loadPlatform(){const box=$('ov-platform');if(!box)return;
  // 平台自身的死活：工作流都正常不代表平台正常——调度器挂了的话
  // 定时任务会静默不跑，而"需要处理"区块要等到逾期才看得出来
  const bits=[];
  bits.push('<span class="pb-item ok">● 远端 '+esc(S.server||'')+'</span>');
  try{const s2=await api('/api/scheduler');
    if(s2.unsupported){bits.push('<span class="pb-item">调度器 未知（远端版本较旧）</span>')}
    else if(s2.alive){const t=s2.seconds_since_tick;
      bits.push('<span class="pb-item ok">● 调度器在跑'+
        (typeof t==='number'?'（'+Math.round(t)+'s 前轮询）':'')+'</span>')}
    else{bits.push('<span class="pb-item bad">● 调度器异常'+
      (s2.last_error?'：'+esc(String(s2.last_error).slice(0,60)):
       (s2.running?'（卡住了，很久没轮询）':'（没在跑）'))+'</span>');
      bits.push('<span class="pb-hint">定时任务不会自动跑了——重启平台服务，'+
        '或看服务端日志里的 scheduler.failed</span>')}}
  catch(e){bits.push('<span class="pb-item">调度器 查不到</span>')}
  box.innerHTML=bits.join('')}
async function loadHealth(){const box=$('ov-health');if(!box)return;
  try{const d=await api('/api/health');
    const bad=(d.items||[]).filter(i=>i.state!=='ok');
    if(!bad.length){box.innerHTML='';return}
    const c=d.counts||{};
    const parts=[];
    if(c.broken)parts.push('坏 '+c.broken);
    if(c.stale)parts.push('停 '+c.stale);
    if(c.waiting)parts.push('等 '+c.waiting);
    box.innerHTML='<div class="section-head"><h2>需要留意</h2>'+
      '<span class="sub">'+parts.join(' · ')+'</span></div>'+
      '<div class="detail" style="margin-top:0;padding:6px 20px">'+bad.map(i=>
        '<div class="hl-row '+(i.state==='broken'?'bad':
          (i.state==='waiting'?'wait':'warn'))+'" '+
        'onclick="gotoWf(\''+i.application_id+'\')" title="点开看这个工作流">'+
        '<span class="hl-st">'+({broken:'✕',stale:'⏸',waiting:'⋯'}[i.state]||'·')+'</span>'+
        '<span class="hl-nm">'+esc(i.workflow)+'</span>'+
        '<span class="hl-rs">'+esc(i.reason)+'</span>'+
        (i.overdue?'<span class="hl-tag">定时没开火</span>':'')+'</div>').join('')+'</div>'}
  catch(e){box.innerHTML=''}}
async function loadOverview(){loadPlatform();loadHealth();try{const d=await api('/api/overview');
  const rt=d.runs_today;
  $('ov-stats').innerHTML=`
    <div class="stat"><div class="num">${rt.total}</div><div class="lbl">今日运行</div></div>
    <div class="stat good"><div class="num">${rt.succeeded}</div><div class="lbl">成功</div></div>
    <div class="stat ${rt.failed?'bad':''}"><div class="num">${rt.failed}</div><div class="lbl">失败</div></div>
    <div class="stat"><div class="num">${d.published_workflows}</div><div class="lbl">已发布工作流</div></div>
    <div class="stat"><div class="num">${d.builds_active}</div><div class="lbl">生成中</div></div>`;
  const wk=d.week||[];
  // other = 跑了但没出结果（排队/进行中/等人工确认）。原来这一柱只算
  // ok+fail，于是"那天 5 条在排队"和"那天什么都没跑"画出来一模一样——
  // 而 CLI 的趋势条特意分了两档（○ 跑了没结果 / · 无运行），
  // 理由是本项目反复写过的那条：**没跑过不等于好**。
  const tot=w=>w.ok+w.fail+(w.other||0);
  if(wk.length){const mx=Math.max(1,...wk.map(tot));
    $('ov-stats').innerHTML+='<div class="week"><div class="lbl">近 7 日</div><div class="bars">'+
      wk.map(w=>{const t=tot(w);const h=t?Math.max(8,Math.round(36*t/mx)):3;
        const fh=t?Math.round(h*w.fail/t):0;
        const oh=t?Math.round(h*(w.other||0)/t):0;
        return '<div class="bar" title="'+w.date+'：成 '+w.ok+' · 败 '+w.fail
          +((w.other||0)?' · 未出结果 '+w.other:'')+'">'+
          (fh?'<div class="b-bad" style="height:'+fh+'px"></div>':'')+
          (oh?'<div class="b-other" style="height:'+oh+'px"></div>':'')+
          '<div class="b-ok" style="height:'+Math.max(0,h-fh-oh)+'px"></div>'+
          '<span>'+w.date.slice(8)+'</span></div>'}).join('')+'</div></div>'}
  $('ov-schedules').innerHTML=d.schedules.map(s=>`<div class="line-item"><b>${esc(s.workflow)}</b>
    <span class="sub2">每天 ${s.at}（${esc(s.timezone)}）</span>
    <span class="right">${s.last_fire_date?'最近触发 '+esc(s.last_fire_date):'尚未触发'}</span></div>`).join('')
    ||'<div class="line-item sub2">还没有定时任务——在生成需求里写"每天X点自动运行"即可</div>';
  // 截了要说：干净地砍掉会让人分不出这是全文还是半截话，
  // 而最能照着做的一句常常在末尾。Python 那份（guanjia/failures.py）
  // 2026-08-30 同一天改的，两处措辞必须一致——有测试钉着。
  const clip=(t,n)=>t.length<=n?t:t.slice(0,n)+'…';
  // count 是「这个毛病一共出现过几次」，at 是最近那一次。
  // 原先写成「工作流 ×13 … 2026-08-28T10:03:36」，两个数贴在一起，
  // 读起来像"那一刻失败了 13 次"。次数和时刻各自带上说明词才不会串。
  // （CLI 和 REPL 走 guanjia/failures.py 的同一套措辞。）
  $('ov-failures').innerHTML=d.recent_failures.map(f=>`<div class="line-item"><b>${esc(f.workflow)}</b>
    <span class="sub2">${esc(clip(f.error||'',60))}</span>
    <span class="right">${f.count>1?'同样的毛病 '+f.count+' 次，最近一次 ':'最近一次 '}${esc(fmtWhen(f.at))} · run ${esc(f.run_id)}</span></div>`).join('')
    ||'<div class="line-item sub2">近期没有失败 🎉</div>';
  // 截了就说一句：几行很容易被读成"就这些"，而第 N 种可能才是要命的那个。
  // 老远端没有 recent_failures_total 时保守处理，判不出来就不吭声。
  const shownFails=(d.recent_failures||[]).length;
  const allFails=(typeof d.recent_failures_total==='number')?d.recent_failures_total:shownFails;
  if(allFails>shownFails){$('ov-failures').innerHTML+=
    '<div class="line-item sub2">还有 '+(allFails-shownFails)+' 种别的毛病没列出来</div>'}}
  catch(e){$('ov-stats').innerHTML='<div class="stat bad"><div class="num">!</div><div class="lbl">'+esc(e.message)+'</div></div>'}}

// 2026-08-28T10:03:36+00:00 → 08-28 10:03
function fmtWhen(at){const t=String(at||'');
  return (t.length>=16&&t[4]==='-'&&(t[10]==='T'||t[10]===' '))?t.slice(5,10)+' '+t.slice(11,16):(t||'时间不详')}

function nearBottom(){const el=$('chat-scroll');return el.scrollHeight-el.scrollTop-el.clientHeight<140}
function renderChat(waiting){const stick=nearBottom();$('chat-col').innerHTML=S.messages.map((m,i)=>{
    if(m.kind==='action')return `<div style="margin:-8px 0 12px 42px;font:11.5px/1.5 ui-monospace,monospace;color:var(--faint)">⚙ ${esc(m.text)}</div>`;
    if(m.kind==='build')return `<div style="margin:0 0 14px 42px;border-left:3px solid var(--accent-line);padding:6px 12px;font:12px/1.7 ui-monospace,monospace;color:var(--sub);white-space:pre-wrap">${esc(m.text)}</div>`;
    if(m.kind==='answerbox')return `<div style="margin:0 0 14px 42px;display:flex;gap:8px;max-width:520px">
      <input id="ab-input" placeholder="回答这个问题…" style="flex:1;border:1px solid var(--accent);border-radius:9px;padding:8px 11px"
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
  // 内部上下文标记先剪掉，**必须在 esc 之前**：esc 会把 < 变成 &lt;，
  // 之后就再也认不出来了，标记会原样显示在对话里。
  // 服务端出口会剪，但流式分片是逐字发的、可能带着它先到屏幕上——
  // 命令行那边为此专门挡了第二道（cli.py 的 _CONTEXT_MARK），
  // 网页壳一直没有。同一个判据没铺满出口，今天第四次。
  t=String(t).replace(/<上下文[^>]*\/>\s*/g,'');
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
  // 和 Python 那边同一条判据：星号必须紧贴非空白，
  // 否则 `** x **` 在网页上是粗体、在终端里不是。
  .replace(/\*\*(?=\S)(.+?)(?<=\S)\*\*/g,'<b>$1</b>')
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
          // 显示用服务端给的中文名（老服务端没有 label，退回 tool）；
          // tool 仍然留在对象里，下面按它找 generate_workflow。
          S.messages.push({role:'assistant',kind:'action',
            text:`${ev.label||ev.tool} → ${ev.summary||''}`,
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

async function showArchived(){
  // 收起来的必须看得见——不然用户不敢按第一下
  let data;
  try{data=await api('/api/workflow/archived')}
  catch(e){alert('查不到已收起的：'+e.message);return}
  if(data.unsupported){alert('这个后端还不支持归档（版本较旧）');return}
  const items=data.items||[];
  if(!items.length){alert('没有收起来的东西。');return}
  const lines=items.slice(0,15).map((i,n)=>(n+1)+'. '+i.name).join('\n');
  const more=items.length>15?('\n…还有 '+(items.length-15)+' 个'):'';
  const answer=prompt('已收起 '+items.length+' 个：\n\n'+lines+more+
    '\n\n要拿回哪个？填序号（1-'+Math.min(15,items.length)+'），或直接关掉。','');
  if(!answer)return;
  const index=parseInt(answer,10)-1;
  if(!(index>=0&&index<Math.min(15,items.length))){alert('序号不对');return}
  try{await api('/api/workflow/archive',{app_id:items[index].id,archived:false});
    alert('已放回：'+items[index].name);boot()}
  catch(e){alert('放回失败：'+e.message)}}
async function tidyWorkflows(){
  // 只给建议、由用户点头——跟对话里那条工具同一个规矩
  let data;
  try{data=await api('/api/workflow/archivable?days=3')}
  catch(e){alert('查不到可收拾的：'+e.message);return}
  if(data.unsupported){alert('这个后端还不支持归档（版本较旧）');return}
  const items=data.items||[];
  if(!items.length){alert('按「从没发布且从没成功跑过」这个标准，没有可收的。');return}
  const preview=items.slice(0,8).map(i=>'· '+i.name+'（跑过 '+i.runs+' 次）').join('\n');
  const more=items.length>8?('\n…还有 '+(items.length-8)+' 个'):'';
  if(!confirm('这些从没发布也从没成功跑过：\n\n'+preview+more+
      '\n\n收起来？数据不会删，之后能拿回来。'))return;
  let done=0,failed=0;
  for(const item of items){
    try{await api('/api/workflow/archive',{app_id:item.id,archived:true});done++}
    catch(e){failed++}
  }
  alert('收起了 '+done+' 个'+(failed?('，'+failed+' 个没成功'):'')+'。');
  boot()}
function togglePub(){S.onlyPub=!S.onlyPub;$('wf-pub').classList.toggle('on',S.onlyPub);renderList()}
function renderList(){const q=($('wf-search').value||'').toLowerCase();
  const list=S.workflows.filter(w=>(!S.onlyPub||w.published)&&(!q||(w.name+w.description).toLowerCase().includes(q)));
  $('wf-count').textContent=list.length+' 个';
  $('wf-list').innerHTML=list.map(w=>`
    <div class="wf-card ${S.current&&S.current.id===w.id?'sel':''}" onclick="openWf('${w.id}')">
      <h4>${esc(w.name)}</h4><div class="desc">${esc(w.description)}</div>
      <span class="badge ${w.published?'b-on':'b-off'}">${w.published?'v'+w.version+' 已发布':'未发布'}</span>
      ${w.published?'':`<button class="wf-archive" title="从列表收起（数据不删）"
        onclick="archiveOne('${w.id}','${esc(w.name).replace(/'/g,"&#39;")}',event)">收起</button>`}
    </div>`).join('')||'<div class="empty">没有匹配的工作流</div>'}
async function archiveOne(id,name,ev){ev.stopPropagation();
  if(!confirm('把「'+name+'」从列表收起来？数据不会删，之后能拿回来。'))return;
  try{const r=await api('/api/workflow/archive',{app_id:id,archived:true});
    // 带定时的工作流收起来会连定时一起停——这是隐式副作用，收完必须说
    if(r.was_scheduled)alert('已收起「'+name+'」。注意：它的定时也一并停了，'+
      '放回列表就会恢复。');
    boot()}
  catch(e){alert('收起失败：'+e.message)}}
async function openWf(id){S.current=S.workflows.find(w=>w.id===id);renderList();
  let schema=[];try{schema=await api('/api/workflow/inputs/'+id)}catch(e){}
  S.schema=schema;
  // 只用 HTML 搭骨架，值一律事后用 DOM 赋——既躲开属性转义/注入，
  // 也不会被 <input value> 把多行示例截成一行（招牌 demo 就栽在这：
  // 三行文本被截成一行，业主拿到 line_count=1 还以为是对的）
  const fields=schema.map(f=>`<div class="field">
    <label>${esc(f.label)}<code>${esc(f.name)} · ${esc(f.type||'string')}</code></label>
    ${needsTextarea(f)?`<textarea data-k="${esc(f.name)}"></textarea>`
                      :`<input data-k="${esc(f.name)}">`}
    <div class="field-err"></div></div>`).join('');
  $('wf-detail').innerHTML=`<div class="detail"><h3>${esc(S.current.name)}
    <span class="badge ${S.current.published?'b-on':'b-off'}">${S.current.published?'v'+S.current.version:'未发布'}</span></h3>
    <div class="meta">${esc(S.current.description)}</div>
    <div id="run-form">${fields||'<div class="empty" style="padding:8px 0">无输入声明，直接运行</div>'}</div>
    <div class="run-row"><button class="primary" ${S.current.published?'':'disabled'} onclick="runWf(this)">运行</button>
    <button onclick="exportWf(this)">导出</button>
    <span class="note">执行发生在远端，本地只接收结果</span></div>
    <div id="run-result"></div>
    <div id="run-history"></div></div>`;
  loadHistory(id);
  document.querySelectorAll('#run-form [data-k]').forEach(el=>{
    const f=schema.find(x=>x.name===el.dataset.k);if(!f)return;
    el.value=(f.example===undefined||f.example===null)?''
      :(typeof f.example==='string'?f.example:JSON.stringify(f.example,null,2))});
  $('wf-detail').scrollIntoView({behavior:'smooth',block:'nearest'})}
async function loadHistory(id){const box=$('run-history');if(!box)return;
  try{const runs=await api('/api/workflow/history/'+id);
    if(!runs.length){box.innerHTML='<div class="empty" style="padding:6px 0">还没跑过</div>';return}
    box.innerHTML='<h4 class="h-title">最近运行（点行看过程）</h4>'+runs.map(r=>{
      const M={succeeded:['ok','✓'],failed:['bad','✕'],cancelled:['warn','⊘'],
        paused:['warn','⏸'],running:['','…'],queued:['','⋯']};
      const [st,mk]=M[r.status]||['','?'];
      const rb=(r.status==='failed'||r.status==='cancelled')?'<button class="h-rerun" onclick="rerunRun(\''+r.id+'\',this,event)">重跑</button>':'';
      return '<div class="h-item"><div class="h-row '+st+'" onclick="toggleEvents(\''+r.id+'\',this)">'+
        '<span class="h-st">'+mk+'</span>'+
        '<span class="h-at">'+esc(r.at)+'</span>'+
        '<span class="h-tx">'+esc(r.error||r.brief||'')+'</span>'+
        '<span class="h-by">'+esc(byLabel(r.by))+'</span>'+rb+'</div>'+
        '<div class="h-ev" id="ev-'+r.id+'"></div></div>'}).join('')}
  catch(e){box.innerHTML=''}}
// 谁起的这次运行。**空不等于定时**——原来这里写的是 `r.by||'⏰ 定时'`，
// 于是所有没记来源的运行都被贴上"定时"的标签，而那里面混着管家代跑的
// 和测试跑的（平台真机上分别是 17 条和 265 条）。
// 平台侧已经让调度器显式记 "schedule"；这里照着翻，翻不出来就
// 如实说"来源没记"——**别把"不知道"说成一个具体答案**。
function byLabel(by){
  const v=(by||'').trim();
  if(!v)return '来源没记';
  if(v==='schedule')return '⏰ 定时';
  if(v==='schedule_manual')return '⏰ 手动补跑';
  return v;                       // 其余是用户名，原样显示
}
async function rerunRun(id,btn,ev){ev.stopPropagation();btn.disabled=true;btn.textContent='重跑中…';
  try{const r=await api('/api/workflow/rerun',{run_id:id});
    btn.textContent=r.status==='succeeded'?'✓ 成功':(r.status==='failed'?'✕ 又失败':'… 运行中')}
  catch(e){btn.textContent='出错'}
  setTimeout(()=>{if(S.current)loadHistory(S.current.id)},1500)}
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
        :'<div class="ev-row"><span class="ev-tx">没有事件记录</span></div>';
      try{const arts=await api('/api/workflow/artifacts/'+id);
        if(arts.length){box.innerHTML+='<div class="ev-arts">'+arts.map(a=>
          '<a class="art" href="/api/workflow/artifact/'+id+'/'+a.name.split('/').map(encodeURIComponent).join('/')+'" download>⬇ '+esc(a.name)+' <i>'+fmtSize(a.size)+'</i></a>').join('')+'</div>'}}
      catch(e){}}
    catch(e){box.innerHTML='<div class="ev-row bad"><span class="ev-tx">'+esc(e.message)+'</span></div>';delete box.dataset.loaded}}}
function fmtSize(n){if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';
  return (n/1048576).toFixed(1)+' MB'}
async function importWf(input){const file=input.files&&input.files[0];if(!file)return;
  input.value='';
  let payload;
  try{payload=JSON.parse(await file.text())}
  catch(e){alert('不是合法 JSON：'+e.message);return}
  const name=prompt('导入后的名字（留空用快照里的）','')||'';
  try{const r=await api('/api/workflow/import',{payload,name});
    let msg='已导入「'+r.name+'」'+(r.published?'并发布':'（草稿，未发布）');
    if(r.skipped_tests)msg+='\n测试无 mandatory 标记已跳过';
    if(r.publish_error)msg+='\n发布被拒：'+r.publish_error+'\n草稿已留好，对话里可以让它补验收';
    alert(msg);boot()}
  catch(e){alert('导入失败：'+e.message)}}
async function exportWf(btn){btn.disabled=true;
  try{const d=await api('/api/workflow/export/'+S.current.id);
    const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);
    a.download=(S.current.name||'workflow')+'.guanjia.json';a.click();
    setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
  catch(e){alert('导出失败：'+e.message)}
  btn.disabled=false}
async function runWf(btn){const inputs={};let bad=false;
  document.querySelectorAll('#run-form [data-k]').forEach(el=>{
    const f=(S.schema||[]).find(x=>x.name===el.dataset.k)||{};
    const box=el.parentElement.querySelector('.field-err');
    try{inputs[el.dataset.k]=coerceInput(el.value,f.type);
      if(box)box.textContent='';el.classList.remove('bad')}
    catch(e){bad=true;el.classList.add('bad');   // 解析失败要看得见，不能静默丢键
      if(box)box.textContent='格式不对：'+e.message}});
  if(bad){$('run-result').innerHTML='<div class="result r-err">有输入格式不对，改好再跑</div>';return}
  // 少了必填项就别发：远端会建一条运行记录、在 start 节点失败，
  // 那条失败永久留在历史里，还会让体检以为工作流坏了
  const missing=(S.schema||[]).filter(f=>f.required!==false
    &&String(inputs[f.name]??'').trim()==='');
  if(missing.length){
    missing.forEach(f=>{const el=document.querySelector(`#run-form [data-k="${f.name}"]`);
      if(el)el.classList.add('bad');
      const box=el&&el.parentElement.querySelector('.field-err');
      if(box)box.textContent='这项必填'});
    $('run-result').innerHTML='<div class="result r-err">还缺必填输入：'
      +missing.map(f=>esc(f.label||f.name)).join('、')+'</div>';return}
  btn.disabled=true;
  const box=$('run-result');box.innerHTML='<div class="result r-ok">远端运行中…</div>';
  try{const r=await api('/api/workflow/run',{app_id:S.current.id,inputs});
    const rows=Object.entries(r.outputs||{}).map(([k,v])=>`<div class="kv"><b>${esc(k)}</b><span>${esc(typeof v==='object'?JSON.stringify(v,null,2):v)}</span></div>`).join('');
    box.innerHTML=r.status==='succeeded'?`<div class="result r-ok">${rows||'(无输出)'}</div>`
      :`<div class="result r-err">${esc(RUN_WORDS[r.status]||'情况不明')}${r.error?'：'+esc(r.error):''}</div>`}
  catch(e){box.innerHTML=`<div class="result r-err">${esc(e.message)}</div>`}
  btn.disabled=false;if(S.current)loadHistory(S.current.id)}
async function generate(){const req=$('gen-req').value.trim();
  if(req.length<10){alert('需求至少 10 个字');return}
  $('gen-btn').disabled=true;const p=$('gen-progress');p.classList.add('show');p.textContent='已提交远端，开始搭建…';
  try{const r=await api('/api/workflow/generate',{requirement:req,
    thinking_enabled:$('gen-think').checked,effort:$('gen-effort').value});
    S.genBuild=r.build_id;pollGen()}
  catch(e){p.textContent='提交失败：'+e.message;$('gen-btn').disabled=false}}
async function pollGen(){if(!S.genBuild)return;
  try{const s=await api('/api/workflow/build/'+S.genBuild);
    $('gen-progress').textContent=`状态 ${s.status} · 草稿修订 ${s.revision??0}`+
      (s.published_version?` · 已发布 v${s.published_version}`:'')+
      (s.pending_question?`\n需要你确认：${s.pending_question}`:'')+
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
          S.messages.push({role:'assistant',text:'构建时遇到一个问题，需要你确认：'+st.pending_question});
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
