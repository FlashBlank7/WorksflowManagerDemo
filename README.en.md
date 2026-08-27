# guanjia (管家)

> **Speak plainly in your terminal; a remote factory builds you a workflow that
> actually runs — on schedule, with audit trails.**

```text
❯ generate a daily GPU status report at 8am
  ⚙ generate_workflow → ⚙ build submitted
● Lilith is on it. Once built it appears in your workflow list and runs at 8:00 daily.

❯ run the GPU report — which card uses the most memory?
  ⚙ run_workflow → ✓ report=card0｜NVIDIA RTX 6000 Ada…
● Cards 1 and 2 are highest (94%) — both held by vLLM.
```

![guanjia demo](docs/demo.gif)

## Why

Conversational terminal agents (aichat, gptme, open-interpreter) edit code and
drive your computer; workflow engines' CLIs (n8n, windmill, temporal) sync YAML.
**The line from "plain language" to "a living, scheduled, monitored workflow"
is empty** — guanjia fills it:

- **Generate**: describe a business need; a server-side builder agent assembles,
  tests, and publishes a runnable workflow (deliverable, not code to copy)
- **Orchestrate**: `guanjia today` — today's runs, schedules, failures at a glance
- **Thin shell**: local client is pure Python, zero dependencies, stores no
  business data; every capability comes from your self-hosted backend

## Install

```bash
uv tool install guanjia    # recommended
uvx guanjia                # try without installing
pipx install guanjia       # alternative
```

## Use

```bash
guanjia            # chat REPL — the signature feature
guanjia --login    # register/login (shared register token + your own password)
guanjia today      # one-glance ops summary, no REPL
guanjia web        # local web shell at 127.0.0.1:7800 (--app opens a desktop-style window)
guanjia run 报表 --json      # run a published workflow from scripts/cron (exit codes)
guanjia run 报表 --follow    # live-stream events while it runs
guanjia rerun a1b2c3d4       # re-run with the original inputs (id prefix is enough)
guanjia export 报表 && guanjia import 报表.guanjia.json --name copy   # move workflows
guanjia remote     # multiple backend profiles: list / use / add / rm
guanjia doctor     # connectivity self-check with plain-language fixes
eval "$(guanjia completion bash)"   # Tab completion (zsh works too)
```

- **Chat is the interface**: streaming answers; workflow builds show progress
  cards inline, and the builder's clarifying questions are answered right in chat
- **Sessions persist** in `~/.guanjia/sessions/`, shared between CLI and web
- **Multi-backend**: keep a profile per environment, switch with one command
- **Web shell = same account, same powers**: login, streaming chat, markdown,
  build tracking, dashboards, auto-rendered run forms, run timelines with
  artifact downloads

## Finding what broke — and fixing it

**Health check**: `guanjia doctor` names the workflows that are broken (all runs
failed in the window, or a recent failure streak) or stalled (scheduled but never
ran), each with the reason from its last failure. The same report shows up in
`guanjia today`, the web dashboard, and in chat ("anything broken?").

**Repair**: say "X is broken, fix it" in chat — the builder works **on the existing
workflow** (it reads the current draft rather than starting over), uses the failure
reason as its lead, adds an acceptance case covering that failure, and republishes.
In practice it also finds related defects the error message never mentioned.

**Alerting**: three layers, use what fits:

1. **Away**: set `ALERT_WEBHOOK_URL` on the backend — any failed run POSTs
   `{workflow, run_id, error, at}` to your DingTalk/Feishu/Slack webhook
   (3s timeout; alerting can never affect the run itself)
2. **Present**: the web shell polls while open — new failures light a red dot
   and raise a browser notification
3. **Digest**: ask in chat for "a daily 9am failure-summary workflow" — the
   builder makes one

## Architecture

```text
guanjia CLI/Web (local, zero-dep)
   │  single channel: HTTPS + session token
   ▼
Lilies platform (self-hosted): builder agent · workflow runtime · scheduler ·
audit ledger · user system
```

Language understanding and every tool call execute server-side
(`/api/v1/assistant/agent`) — the client is a thin REPL, so audits are complete
and clients cannot fake results. Passwords never touch disk locally; only
session tokens are stored (`~/.guanjia.json`).

Design choices worth knowing:

- **Honest by construction**: builds are incremental validated operations
  (never one-shot JSON); empty upstreams produce honest empty results; the
  assistant answers with numbers traceable to the ledger
- **Self-hosted backend**: your models (DeepSeek or any OpenAI-compatible,
  local vLLM supported), your data, your audit log

## Development

```bash
uv tool install --editable --from . guanjia
python3 -m unittest discover tests    # zero-dep regression suite
```

MIT License. · [中文 README](README.md) · [alternatives](docs/alternatives.md)
