"""bench 本地壳：localhost 单页界面，一切能力经插件转发远端。

用法：python3 -m bench.app --server http://<平台>:8000 --token <API_TOKEN> [--port 7800]
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import load_config
from .plugins import PLUGINS, assistant, workflow
from .remote import RemoteClient, RemoteError


class Handler(BaseHTTPRequestHandler):
    remote: RemoteClient

    def log_message(self, *args) -> None:
        pass

    def _json(self, data, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        try:
            if self.path == "/":
                body = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/bootstrap":
                connected, detail = True, ""
                try:
                    self.remote.health()
                except Exception as error:
                    connected, detail = False, str(error)[:120]
                self._json({
                    "server": self.remote.server,
                    "connected": connected,
                    "detail": detail,
                    "plugins": PLUGINS,
                    "workflows": workflow.list_workflows(self.remote) if connected else [],
                })
            elif self.path.startswith("/api/workflow/build/"):
                self._json(workflow.build_status(self.remote, self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/inputs/"):
                self._json(workflow.input_schema(self.remote, self.path.rsplit("/", 1)[1]))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/api/chat":
                self._json(assistant.chat(self.remote, body.get("messages") or []))
            elif self.path == "/api/workflow/generate":
                self._json(workflow.generate(
                    self.remote,
                    str(body.get("requirement") or ""),
                    bool(body.get("thinking_enabled", False)),
                    str(body.get("effort") or "low"),
                ))
            elif self.path == "/api/workflow/run":
                self._json(workflow.run(self.remote, body["app_id"], body.get("inputs") or {}))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="bench — 本地工作台（远端服务客户端）")
    parser.add_argument("--server", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--port", type=int, default=7800)
    args = parser.parse_args()
    cfg = load_config(args.server, args.token)
    Handler.remote = RemoteClient(cfg["server"], cfg["token"])
    print(f"bench: http://127.0.0.1:{args.port}  →  远端 {cfg['server']}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


PAGE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>bench 工作台</title>
<style>
:root{--bg:#f4f6f9;--panel:#fff;--ink:#1a1f27;--muted:#69727f;--line:#e4e8ee;--accent:#0e7a5f;--soft:#e8f5ef;--warn:#8a5a00;--warnbg:#fff6e6;--err:#b42318;--errbg:#fef3f2}
*{box-sizing:border-box}body{margin:0;font:14px/1.65 -apple-system,"PingFang SC",sans-serif;background:var(--bg);color:var(--ink);height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:12px;padding:12px 22px;background:var(--panel);border-bottom:1px solid var(--line)}
header b{font-size:15px}header .conn{font-size:12px;color:var(--muted)}
header .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.on{background:#22a06b}.off{background:var(--err)}
nav{display:flex;gap:4px;margin-left:auto}
nav button{border:0;background:none;padding:7px 14px;border-radius:8px;font-size:13px;color:var(--muted);cursor:pointer}
nav button.act{background:var(--soft);color:var(--accent);font-weight:600}
main{flex:1;overflow:hidden;display:flex}
.view{flex:1;overflow-y:auto;padding:20px;display:none}
.view.act{display:block}
.inner{max-width:820px;margin:0 auto}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
.card h3{margin:0 0 8px;font-size:14.5px}
textarea,input,select{border:1px solid var(--line);border-radius:8px;padding:9px 11px;font:13px/1.5 inherit;width:100%}
textarea{resize:vertical;min-height:70px}
.row{display:flex;gap:10px;align-items:center;margin-top:10px}
.btn{border:0;border-radius:9px;background:var(--accent);color:#fff;padding:9px 20px;font-size:13.5px;cursor:pointer;white-space:nowrap}
.btn:disabled{opacity:.5}
.muted{color:var(--muted);font-size:12.5px}
/* chat */
#chat-view{display:none;flex-direction:column;height:100%}
#chat-view.act{display:flex}
.chat-scroll{flex:1;overflow-y:auto;padding:20px}
.msg{max-width:820px;margin:0 auto 16px;display:flex;gap:10px}
.avatar{flex:none;width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-size:11px;font-weight:700}
.msg.user .avatar{background:#e8ecf2;color:#5a6472}.msg.bot .avatar{background:var(--accent);color:#fff}
.bubble{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:10px 14px;white-space:pre-wrap;word-break:break-word;min-width:0}
.msg.user .bubble{background:#eef2f7}
.composer{border-top:1px solid var(--line);background:var(--panel);padding:12px 20px}
.composer .inner{display:flex;gap:10px}
.composer textarea{min-height:46px;max-height:120px}
/* workflow */
.wf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.wf-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;cursor:pointer}
.wf-card:hover{border-color:var(--accent)}
.wf-card h4{margin:0 0 4px;font-size:14px}
.badge{font-size:11px;border-radius:99px;padding:2px 9px}
.b-on{background:var(--soft);color:var(--accent)}.b-off{background:var(--warnbg);color:var(--warn)}
.result{border-radius:10px;padding:12px;margin-top:12px;font-size:13px;border:1px solid}
.r-ok{background:#f7fcfa;border-color:#c4e6d8}.r-err{background:var(--errbg);border-color:#f0b4ae}
.kv{display:flex;gap:10px;padding:3px 0;border-bottom:1px dashed var(--line)}
.kv:last-child{border:0}.kv b{flex:none;min-width:90px;color:var(--muted);font-weight:500}
.kv span{white-space:pre-wrap;word-break:break-word}
.progress{font:12px/1.7 ui-monospace,Menlo,monospace;color:var(--muted);white-space:pre-wrap}
.field{margin-top:9px}.field label{display:block;font-size:12px;color:var(--muted);margin-bottom:3px}
</style></head>
<body>
<header><b>▸ bench</b><span class="conn" id="conn">连接中…</span>
<nav><button id="nav-chat" class="act" onclick="show('chat')">对话</button><button id="nav-wf" onclick="show('wf')">工作流</button></nav>
</header>
<main>
  <div id="chat-view" class="act">
    <div class="chat-scroll" id="chat-scroll"></div>
    <div class="composer"><div class="inner" style="max-width:820px;margin:0 auto">
      <textarea id="chat-input" placeholder="问点什么——回答由远端服务生成"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea>
      <button class="btn" onclick="send()">发送</button>
    </div></div>
  </div>
  <div id="wf-view" class="view"><div class="inner">
    <div class="card"><h3>生成新工作流（远端莉莉丝）</h3>
      <textarea id="gen-req" placeholder="用业务语言描述需求，例如：每天早上8点生成服务器GPU状态日报…"></textarea>
      <div class="row">
        <label class="muted"><input type="checkbox" id="gen-think" style="width:auto"> 深度思考</label>
        <select id="gen-effort" style="width:110px"><option value="low">effort: low</option><option value="medium">medium</option><option value="high">high</option></select>
        <button class="btn" id="gen-btn" onclick="generate()">开始生成</button>
      </div>
      <div class="progress" id="gen-progress"></div>
    </div>
    <h3 style="font-size:13px;color:var(--muted);margin:16px 0 10px">已有工作流</h3>
    <div class="wf-grid" id="wf-list"></div>
    <div id="wf-detail"></div>
  </div></div>
</main>
<script>
let S={messages:[],workflows:[],current:null,genBuild:null};
const $=id=>document.getElementById(id);
async function api(path,body){const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw new Error(d.error||r.status);return d}
function esc(t){return String(t??'').replace(/&/g,'&amp;').replace(/</g,'&lt;')}
async function boot(){try{const d=await api('/api/bootstrap');
  $('conn').innerHTML=`<span class="dot ${d.connected?'on':'off'}"></span>${d.connected?'已连接远端':'远端不可达'} · ${esc(d.server)}${d.detail?' · '+esc(d.detail):''}`;
  S.workflows=d.workflows;renderList()}catch(e){$('conn').innerHTML=`<span class="dot off"></span>${esc(e.message)}`}}
function show(v){['chat','wf'].forEach(x=>{
  (x==='chat'?$('chat-view'):$('wf-view')).classList.toggle('act',x===v);
  $('nav-'+(x==='wf'?'wf':'chat')).classList.toggle('act',x===v)});if(v==='wf')boot()}
function pushMsg(role,text){S.messages.push({role,text});
  $('chat-scroll').innerHTML=S.messages.map(m=>`<div class="msg ${m.role==='user'?'user':'bot'}">
    <div class="avatar">${m.role==='user'?'我':'远'}</div><div class="bubble">${esc(m.text)}</div></div>`).join('');
  $('chat-scroll').scrollTop=$('chat-scroll').scrollHeight}
async function send(){const t=$('chat-input').value.trim();if(!t)return;$('chat-input').value='';
  pushMsg('user',t);pushMsg('assistant','…');
  try{const r=await api('/api/chat',{messages:S.messages.filter(m=>m.text!=='…')});
    S.messages.pop();pushMsg('assistant',r.text||'(空回复)')}
  catch(e){S.messages.pop();pushMsg('assistant','远端出错：'+e.message)}}
function renderList(){$('wf-list').innerHTML=S.workflows.map(w=>`
  <div class="wf-card" onclick="openWf('${w.id}')"><h4>${esc(w.name)}</h4>
  <div class="muted" style="font-size:12px;margin-bottom:6px">${esc(w.description).slice(0,60)}</div>
  <span class="badge ${w.published?'b-on':'b-off'}">${w.published?'v'+w.version+' 已发布':'未发布'}</span></div>`).join('')
  ||'<div class="muted">远端还没有工作流，用上方生成一个。</div>'}
async function openWf(id){S.current=S.workflows.find(w=>w.id===id);
  let schema=[];try{schema=await api('/api/workflow/inputs/'+id)}catch(e){}
  const fields=schema.map(f=>{const isObj=typeof f.example==='object';
    return `<div class="field"><label>${esc(f.label)} <span style="color:#aab">${f.name}·${f.type}</span></label>
    ${isObj?`<textarea data-k="${f.name}" data-json="1">${esc(JSON.stringify(f.example,null,2))}</textarea>`
          :`<input data-k="${f.name}" value="${esc(f.example)}">`}</div>`}).join('');
  $('wf-detail').innerHTML=`<div class="card" style="margin-top:14px"><h3>${esc(S.current.name)}
    ${S.current.published?`<span class="badge b-on">v${S.current.version}</span>`:'<span class="badge b-off">未发布</span>'}</h3>
    <div id="run-form">${fields||'<div class="muted">无输入声明（直接运行）</div>'}</div>
    <div class="row"><button class="btn" ${S.current.published?'':'disabled'} onclick="runWf(this)">运行</button>
    <span class="muted">执行发生在远端，本地只收结果</span></div><div id="run-result"></div></div>`;
  $('wf-detail').scrollIntoView({behavior:'smooth'})}
async function runWf(btn){btn.disabled=true;const inputs={};
  document.querySelectorAll('#run-form [data-k]').forEach(el=>{
    try{inputs[el.dataset.k]=el.dataset.json?JSON.parse(el.value):el.value}catch(e){}});
  const box=$('run-result');box.innerHTML='<div class="muted" style="margin-top:10px">远端运行中…</div>';
  try{const r=await api('/api/workflow/run',{app_id:S.current.id,inputs});
    const rows=Object.entries(r.outputs||{}).map(([k,v])=>`<div class="kv"><b>${esc(k)}</b><span>${esc(typeof v==='object'?JSON.stringify(v,null,2):v)}</span></div>`).join('');
    box.innerHTML=r.status==='succeeded'?`<div class="result r-ok">${rows||'(无输出)'}</div>`
      :`<div class="result r-err">状态 ${esc(r.status)}：${esc(r.error||'')}</div>`}
  catch(e){box.innerHTML=`<div class="result r-err">${esc(e.message)}</div>`}
  btn.disabled=false}
async function generate(){const req=$('gen-req').value.trim();if(req.length<10){alert('需求至少10个字');return}
  $('gen-btn').disabled=true;$('gen-progress').textContent='已提交远端，莉莉丝开工…';
  try{const r=await api('/api/workflow/generate',{requirement:req,
    thinking_enabled:$('gen-think').checked,effort:$('gen-effort').value});
    S.genBuild=r.build_id;pollGen()}
  catch(e){$('gen-progress').textContent='提交失败：'+e.message;$('gen-btn').disabled=false}}
async function pollGen(){if(!S.genBuild)return;
  try{const s=await api('/api/workflow/build/'+S.genBuild);
    $('gen-progress').textContent=`状态 ${s.status} · 草稿版本 ${s.revision}`+
      (s.published_version?` · 已发布 v${s.published_version}`:'')+
      (s.pending_question?`\n莉莉丝提问：${s.pending_question}`:'')+
      (s.narration?`\n她说：${s.narration}`:'')+(s.error?`\n错误：${s.error}`:'');
    if(['published','ready','needs_attention','failed','cancelled'].includes(s.status)){
      $('gen-btn').disabled=false;boot();return}
  }catch(e){}
  setTimeout(pollGen,4000)}
boot();
</script></body></html>
"""


if __name__ == "__main__":
    main()
