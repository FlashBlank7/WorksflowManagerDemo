"""guanjia 本地壳：localhost 单页界面，一切能力经插件转发远端。

用法：guanjia web [--port 7800]
首次打开进入连接页：填远端地址 + 个人令牌（管理员在平台上用
POST /api/v1/users 为每人签发），保存于 ~/.bench.json。
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_config
from .plugins import PLUGINS, assistant, workflow
from .remote import RemoteClient, RemoteError


class Handler(BaseHTTPRequestHandler):
    remote: RemoteClient | None = None

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

    def _need_remote(self) -> RemoteClient:
        if self.remote is None or not self.remote.token:
            raise RemoteError(401, "未配置远端连接")
        return self.remote

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
                if self.remote is None or not self.remote.token:
                    self._json({"configured": False, "plugins": PLUGINS})
                    return
                try:
                    me = self.remote.request("GET", "/api/v1/me")["user"]
                    self._json({
                        "configured": True, "connected": True,
                        "server": self.remote.server, "user": me, "plugins": PLUGINS,
                        "workflows": workflow.list_workflows(self.remote),
                    })
                except Exception as error:
                    self._json({"configured": True, "connected": False,
                                "server": self.remote.server, "detail": str(error)[:150],
                                "plugins": PLUGINS, "workflows": []})
            elif self.path == "/api/overview":
                self._json(self._need_remote().request("GET", "/api/v1/overview"))
            elif self.path.startswith("/api/workflow/build/"):
                self._json(workflow.build_status(self._need_remote(), self.path.rsplit("/", 1)[1]))
            elif self.path.startswith("/api/workflow/inputs/"):
                self._json(workflow.input_schema(self._need_remote(), self.path.rsplit("/", 1)[1]))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/api/config":
                server = str(body.get("server") or "").rstrip("/")
                mode = str(body.get("mode") or "login")
                anon = RemoteClient(server, "")
                if mode == "register":
                    result = anon.request("POST", "/api/v1/auth/register", {
                        "register_token": str(body.get("register_token") or ""),
                        "name": str(body.get("name") or ""),
                        "password": str(body.get("password") or ""),
                    })
                else:
                    result = anon.request("POST", "/api/v1/auth/login", {
                        "name": str(body.get("name") or ""),
                        "password": str(body.get("password") or ""),
                    })
                token = result["token"]  # 只存会话令牌，密码不落盘
                (Path.home() / ".guanjia.json").write_text(
                    json.dumps({"server": server, "token": token}, ensure_ascii=False), encoding="utf-8"
                )
                Handler.remote = RemoteClient(server, token)
                self._json({"ok": True, "user": result["user"]})
            elif self.path == "/api/chat":
                self._json(assistant.chat(self._need_remote(), body.get("messages") or []))
            elif self.path == "/api/workflow/generate":
                self._json(workflow.generate(
                    self._need_remote(),
                    str(body.get("requirement") or ""),
                    bool(body.get("thinking_enabled", False)),
                    str(body.get("effort") or "low"),
                ))
            elif self.path == "/api/workflow/run":
                self._json(workflow.run(self._need_remote(), body["app_id"], body.get("inputs") or {}))
            else:
                self._json({"error": "not found"}, 404)
        except RemoteError as error:
            self._json({"error": str(error)}, 401 if error.status == 401 else 502)
        except Exception as error:  # noqa: BLE001
            self._json({"error": str(error)}, 500)


def main() -> None:
    parser = argparse.ArgumentParser(description="guanjia — 本地工作台（远端服务客户端）")
    parser.add_argument("--server", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--port", type=int, default=7800)
    args = parser.parse_args()
    cfg = load_config(args.server, args.token)
    if cfg["token"]:
        Handler.remote = RemoteClient(cfg["server"], cfg["token"])
    print(f"guanjia: http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


PAGE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管家 guanjia</title>
<style>
:root{
  --bg:#f5f7fa;--panel:#ffffff;--ink:#141a22;--sub:#5c6675;--faint:#98a1af;
  --line:#e6e9ef;--line-soft:#eef1f5;
  --accent:#0e7a5f;--accent-deep:#0a5c48;--accent-soft:#e7f4ef;--accent-line:#bfe3d5;
  --warn:#8a5a00;--warn-bg:#fff6e3;--err:#b42318;--err-bg:#fdf1f0;
  --radius:14px;--shadow:0 1px 2px rgba(20,26,34,.05),0 6px 24px rgba(20,26,34,.06);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font:14px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased}
button{font:inherit;cursor:pointer}
input,textarea,select{font:inherit;color:var(--ink)}
::placeholder{color:var(--faint)}

/* ── 登录页 ── */
#login{position:fixed;inset:0;display:none;place-items:center;background:
  radial-gradient(600px 300px at 70% 20%,#e3efe9 0,transparent 60%),var(--bg)}
#login.show{display:grid}
.login-card{width:380px;background:var(--panel);border:1px solid var(--line);
  border-radius:18px;box-shadow:var(--shadow);padding:30px 30px 26px}
.login-card .logo{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.login-card .logo i{width:34px;height:34px;border-radius:10px;font-style:normal;
  background:linear-gradient(135deg,#0e7a5f,#35b88e);display:grid;place-items:center;color:#fff;font-weight:800}
.login-card .logo b{font-size:18px;letter-spacing:-.01em}
.login-card p{margin:2px 0 20px;color:var(--sub);font-size:13px}
.login-card label{display:block;font-size:12.5px;color:var(--sub);margin:14px 0 6px}
.login-card input{width:100%;border:1px solid var(--line);border-radius:10px;padding:10px 13px;outline:none}
.login-card input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.login-card .go{width:100%;margin-top:22px;border:0;border-radius:11px;background:var(--accent);
  color:#fff;padding:11px;font-size:14.5px;font-weight:600}
.login-card .go:hover{background:var(--accent-deep)}
.login-err{margin-top:12px;font-size:12.5px;color:var(--err);min-height:18px}

/* ── 主框架 ── */
#shell{display:none;height:100vh}
#shell.show{display:flex}
aside{width:200px;background:var(--panel);border-right:1px solid var(--line);
  display:flex;flex-direction:column;padding:18px 12px 14px}
aside .logo{display:flex;align-items:center;gap:9px;padding:0 8px 16px}
aside .logo i{width:28px;height:28px;border-radius:9px;font-style:normal;
  background:linear-gradient(135deg,#0e7a5f,#35b88e);display:grid;place-items:center;color:#fff;font-weight:800;font-size:13px}
aside .logo b{font-size:15.5px}
.nav-btn{display:flex;align-items:center;gap:10px;width:100%;border:0;background:none;
  padding:10px 12px;border-radius:10px;color:var(--sub);font-size:13.5px;margin-bottom:2px}
.nav-btn:hover{background:var(--line-soft)}
.nav-btn.act{background:var(--accent-soft);color:var(--accent);font-weight:600}
.nav-btn .ic{width:18px;text-align:center}
aside .spacer{flex:1}
.user-chip{display:flex;align-items:center;gap:9px;padding:9px 10px;border:1px solid var(--line);
  border-radius:11px;font-size:12.5px}
.user-chip .dot{width:26px;height:26px;border-radius:8px;background:var(--accent-soft);
  color:var(--accent);display:grid;place-items:center;font-weight:700;font-size:12px}
.user-chip .who b{display:block;font-size:12.5px;line-height:1.3}
.user-chip .who small{color:var(--faint);font-size:11px}
.conn-note{margin-top:8px;font-size:11px;color:var(--faint);padding:0 4px;word-break:break-all}

main{flex:1;min-width:0;display:flex;flex-direction:column}

/* ── 对话 ── */
#view-chat{flex:1;display:none;flex-direction:column;min-height:0}
#view-chat.act{display:flex}
.chat-scroll{flex:1;overflow-y:auto;padding:30px 24px 10px}
.chat-col{max-width:760px;margin:0 auto}
.msg{display:flex;gap:12px;margin-bottom:20px}
.msg .av{flex:none;width:30px;height:30px;border-radius:9px;display:grid;place-items:center;font-size:11.5px;font-weight:700}
.msg.user .av{background:#e9edf3;color:#5c6675}
.msg.bot .av{background:var(--accent);color:#fff}
.msg .bd{min-width:0;background:var(--panel);border:1px solid var(--line);border-radius:13px;
  padding:11px 15px;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 2px rgba(20,26,34,.03)}
.msg.user .bd{background:#eef2f7;border-color:transparent}
.msg .bd.wait i{font-style:normal;animation:blink 1.2s infinite}
@keyframes blink{50%{opacity:.25}}
.chat-empty{text-align:center;color:var(--faint);padding:80px 0 0}
.chat-empty .big{font-size:34px;margin-bottom:10px}
.composer{border-top:1px solid var(--line);background:var(--panel);padding:14px 24px 16px}
.composer .inner{max-width:760px;margin:0 auto;display:flex;gap:10px;align-items:flex-end;
  border:1px solid var(--line);border-radius:14px;padding:8px 8px 8px 14px;background:var(--bg)}
.composer .inner:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.composer textarea{flex:1;border:0;background:none;outline:none;resize:none;max-height:140px;padding:6px 0}
.send{border:0;border-radius:10px;background:var(--accent);color:#fff;width:40px;height:38px;font-size:16px}
.send:hover{background:var(--accent-deep)}
.composer .hint{max-width:760px;margin:8px auto 0;font-size:11.5px;color:var(--faint)}

/* ── 总览 ── */
.stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:8px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px;box-shadow:0 1px 2px rgba(20,26,34,.03)}
.stat .num{font-size:26px;font-weight:700;letter-spacing:-.02em}
.stat .lbl{font-size:12px;color:var(--sub);margin-top:2px}
.stat.good .num{color:var(--accent)}.stat.bad .num{color:var(--err)}
.line-item{display:flex;gap:12px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line-soft);font-size:13px}
.line-item:last-child{border:0}
.line-item b{font-weight:600}
.line-item .sub2{color:var(--faint);font-size:12px}
.line-item .right{margin-left:auto;color:var(--sub);font-size:12px}

/* ── 工作流 ── */
#view-wf{flex:1;display:none;overflow-y:auto;padding:26px 28px}
#view-wf.act{display:block}
.wf-col{max-width:880px;margin:0 auto}
.section-head{display:flex;align-items:baseline;gap:12px;margin:22px 0 12px}
.section-head h2{margin:0;font-size:15px}
.section-head .count{color:var(--faint);font-size:12px}
.section-head .tools{margin-left:auto;display:flex;gap:8px;align-items:center}
.search{border:1px solid var(--line);border-radius:9px;padding:7px 12px;font-size:13px;width:180px;outline:none;background:var(--panel)}
.search:focus{border-color:var(--accent)}
.chip-toggle{border:1px solid var(--line);background:var(--panel);border-radius:99px;
  padding:5px 13px;font-size:12px;color:var(--sub)}
.chip-toggle.on{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent);font-weight:600}
.gen-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:18px 20px}
.gen-card h2{margin:0 0 4px;font-size:15px}
.gen-card .sub{color:var(--sub);font-size:12.5px;margin-bottom:12px}
.gen-card textarea{width:100%;border:1px solid var(--line);border-radius:11px;padding:11px 13px;
  min-height:76px;resize:vertical;outline:none;background:var(--bg)}
.gen-card textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.gen-row{display:flex;gap:14px;align-items:center;margin-top:12px;flex-wrap:wrap}
.gen-row label{font-size:12.5px;color:var(--sub);display:flex;align-items:center;gap:6px}
.gen-row select{border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:12.5px;background:var(--panel)}
.primary{border:0;border-radius:10px;background:var(--accent);color:#fff;padding:9px 22px;font-size:13.5px;font-weight:600}
.primary:hover{background:var(--accent-deep)}
.primary:disabled{opacity:.5;cursor:default}
.gen-progress{margin-top:12px;font:12px/1.8 ui-monospace,Menlo,monospace;color:var(--sub);
  white-space:pre-wrap;border-left:3px solid var(--accent-line);padding-left:12px;display:none}
.gen-progress.show{display:block}
.wf-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.wf-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 17px;cursor:pointer;transition:.15s;box-shadow:0 1px 2px rgba(20,26,34,.03)}
.wf-card:hover{transform:translateY(-2px);box-shadow:var(--shadow);border-color:var(--accent-line)}
.wf-card.sel{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.wf-card h4{margin:0 0 5px;font-size:14px}
.wf-card .desc{color:var(--sub);font-size:12px;line-height:1.55;height:37px;overflow:hidden;margin-bottom:9px}
.badge{font-size:11px;border-radius:99px;padding:2.5px 10px}
.b-on{background:var(--accent-soft);color:var(--accent)}
.b-off{background:var(--warn-bg);color:var(--warn)}
.empty{color:var(--faint);text-align:center;padding:40px 0;font-size:13px}
.detail{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  box-shadow:var(--shadow);padding:20px;margin-top:16px}
.detail h3{margin:0 0 2px;font-size:15.5px;display:flex;align-items:center;gap:10px}
.detail .meta{color:var(--faint);font-size:12px;margin-bottom:12px}
.field{margin-top:11px}
.field label{display:block;font-size:12.5px;color:var(--sub);margin-bottom:5px}
.field label code{color:var(--faint);font-size:11px;margin-left:6px}
.field input,.field textarea{width:100%;border:1px solid var(--line);border-radius:9px;
  padding:9px 11px;outline:none;background:var(--bg)}
.field textarea{font:12px/1.6 ui-monospace,Menlo,monospace;min-height:84px;resize:vertical}
.field input:focus,.field textarea:focus{border-color:var(--accent)}
.run-row{display:flex;gap:12px;align-items:center;margin-top:14px}
.run-row .note{font-size:12px;color:var(--faint)}
.result{border-radius:11px;padding:14px 16px;margin-top:14px;border:1px solid;font-size:13px}
.r-ok{background:#f6fbf9;border-color:var(--accent-line)}
.r-err{background:var(--err-bg);border-color:#f0b4ae}
.kv{display:flex;gap:12px;padding:5px 0;border-bottom:1px dashed var(--line)}
.kv:last-child{border:0}
.kv b{flex:none;min-width:96px;color:var(--sub);font-weight:500}
.kv span{white-space:pre-wrap;word-break:break-word;min-width:0}
</style></head>
<body>

<div id="login">
  <div class="login-card">
    <div class="logo"><i>▸</i><b>管家</b></div>
    <p>本地工作台 · 所有能力由远端平台提供</p>
    <label>远端平台地址</label>
    <input id="lg-server" placeholder="http://服务器:8000" value="">
    <label>用户名</label>
    <input id="lg-name" placeholder="你的用户名">
    <label>密码</label>
    <input id="lg-pass" type="password" placeholder="至少 6 位">
    <div id="lg-reg-row" style="display:none">
      <label>注册令牌</label>
      <input id="lg-reg" type="password" placeholder="团队共享的注册令牌">
    </div>
    <button class="go" id="lg-go" onclick="saveConfig()">登录</button>
    <div style="text-align:center;margin-top:12px">
      <a href="#" id="lg-switch" onclick="toggleMode();return false"
         style="font-size:12.5px;color:var(--accent);text-decoration:none">没有账号？注册（首个注册者自动成为管理员）</a>
    </div>
    <div class="login-err" id="lg-err"></div>
  </div>
</div>

<div id="shell">
  <aside>
    <div class="logo"><i>▸</i><b>管家</b></div>
    <button class="nav-btn act" id="nav-chat" onclick="show('chat')"><span class="ic">💬</span>对话</button>
    <button class="nav-btn" id="nav-ov" onclick="show('ov')"><span class="ic">📊</span>总览</button>
    <button class="nav-btn" id="nav-wf" onclick="show('wf')"><span class="ic">⚙️</span>工作流</button>
    <div class="spacer"></div>
    <div class="user-chip"><div class="dot" id="u-dot">?</div>
      <div class="who"><b id="u-name">…</b><small id="u-role"></small></div></div>
    <div class="conn-note" id="conn-note"></div>
  </aside>
  <main>
    <div id="view-chat" class="act">
      <div class="chat-scroll" id="chat-scroll"><div class="chat-col" id="chat-col">
        <div class="chat-empty"><div class="big">💬</div>问点什么——回答由远端服务生成</div>
      </div></div>
      <div class="composer">
        <div class="inner">
          <textarea id="chat-input" rows="1" placeholder="输入消息，Enter 发送"
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea>
          <button class="send" onclick="send()">↑</button>
        </div>
        <div class="hint">本地不运行模型；对话内容发送至远端平台处理</div>
      </div>
    </div>
    <div id="view-ov" class="view-page" style="flex:1;display:none;overflow-y:auto;padding:26px 28px">
      <div class="wf-col">
        <div class="stat-row" id="ov-stats"></div>
        <div class="section-head"><h2>定时任务</h2></div>
        <div class="detail" style="margin-top:0;padding:6px 20px" id="ov-schedules"></div>
        <div class="section-head"><h2>近期失败</h2></div>
        <div class="detail" style="margin-top:0;padding:6px 20px" id="ov-failures"></div>
      </div>
    </div>
    <div id="view-wf"><div class="wf-col">
      <div class="gen-card">
        <h2>生成新工作流</h2>
        <div class="sub">用业务语言描述需求，远端莉莉丝自动搭建、测试、发布</div>
        <textarea id="gen-req" placeholder="例如：输入一段中文文本，输出一句话摘要和字数统计"></textarea>
        <div class="gen-row">
          <label><input type="checkbox" id="gen-think"> 深度思考</label>
          <select id="gen-effort"><option value="low">快速档</option><option value="medium">均衡档</option><option value="high">深思档</option></select>
          <span style="flex:1"></span>
          <button class="primary" id="gen-btn" onclick="generate()">开始生成</button>
        </div>
        <div class="gen-progress" id="gen-progress"></div>
      </div>
      <div class="section-head"><h2>我的工作流</h2><span class="count" id="wf-count"></span>
        <div class="tools">
          <input class="search" id="wf-search" placeholder="搜索…" oninput="renderList()">
          <button class="chip-toggle on" id="wf-pub" onclick="togglePub()">只看已发布</button>
        </div></div>
      <div class="wf-grid" id="wf-list"></div>
      <div id="wf-detail"></div>
    </div></div>
  </main>
</div>

<script>
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
    <span class="sub2">${esc(f.error||'').slice(0,60)}</span><span class="right">${esc(f.at)}</span></div>`).join('')
    ||'<div class="line-item sub2">近期没有失败 🎉</div>'}
  catch(e){$('ov-stats').innerHTML='<div class="stat bad"><div class="num">!</div><div class="lbl">'+esc(e.message)+'</div></div>'}}

function pushMsg(role,text,wait){S.messages.push({role,text});
  $('chat-col').innerHTML=S.messages.map((m,i)=>`<div class="msg ${m.role==='user'?'user':'bot'}">
    <div class="av">${m.role==='user'?'我':'远'}</div>
    <div class="bd${wait&&i===S.messages.length-1?' wait':''}">${esc(m.text)}${wait&&i===S.messages.length-1?'<i>…</i>':''}</div></div>`).join('');
  $('chat-scroll').scrollTop=$('chat-scroll').scrollHeight}
async function send(){const t=$('chat-input').value.trim();if(!t)return;$('chat-input').value='';
  pushMsg('user',t);pushMsg('assistant','',true);
  try{const r=await api('/api/chat',{messages:S.messages.filter(m=>m.text)});
    S.messages.pop();pushMsg('assistant',r.text||'(空回复)')}
  catch(e){S.messages.pop();pushMsg('assistant','远端出错：'+e.message)}}

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
</script></body></html>
"""


if __name__ == "__main__":
    main()
