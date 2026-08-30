# WorksflowManagerDemo

> **guanjia (管家) — say what you need in your terminal; get a workflow
> that actually runs, on schedule, and keeps running.**

You describe the need in one sentence. What comes back isn't code to wire up
yourself — it's **something already running**: versioned, scheduled, and it
tells you when it breaks.

```text
❯ generate a daily GPU status report at 8am
  ⚙ generate_workflow → ⚙ build submitted
● Lilith is on it. Once built it appears in your workflow list and runs at 8:00 daily.

❯ run the GPU report — which card uses the most memory?
  ⚙ run_workflow → ✓ report=card0｜NVIDIA RTX 6000 Ada…
● Cards 1 and 2 are highest (94%) — both held by vLLM.
```

![guanjia demo](docs/demo.gif)

*Real recording: `doctor` for platform status → `today` for runs and the 7-day trend → ask in chat, run a workflow, get real data.*

## First, the catch: it needs a backend

guanjia is a **thin client** — installing it does not conjure a workflow
platform. Every capability comes from a backend you deploy yourself (or that a
colleague already runs). What the trade buys: the agent loop and every tool call
execute server-side and land in an audit ledger, so **the client cannot fake
results**. What it costs: there is no hosted version — you need a backend first.
See [the backend section](#the-backend-it-talks-to).

## Why

Conversational terminal agents (aichat, gptme, open-interpreter) edit code and
drive your computer, then they're done; workflow engines' CLIs (n8n, windmill,
temporal) target engineers who already write YAML.
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
pipx install guanjia       # or this
uvx guanjia --version      # just checking it installed
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

Exit codes for `guanjia run` / `rerun` are a promise to your scripts, not an
implementation detail:

| Code | Meaning | What a script should do |
|------|---------|-------------------------|
| 0 | Succeeded | carry on |
| 1 | Did not succeed (failed or cancelled) | treat as a failure |
| 2 | Wrong usage (no such workflow, argument not `k=v`, missing required input) | fix the command, not the workflow |
| 3 | Status this client does not recognise | treat as a failure and check the backend version |
| 4 | Paused, waiting for human input | do not retry; go fill that step in |

Keep 2 apart from 1: one means your command was wrong, the other means the
workflow really did not succeed.

- **Chat is the interface**: streaming answers; workflow builds show progress
  cards inline, and the builder's clarifying questions are answered right in chat
- **Sessions persist** in `~/.guanjia/sessions/`, shared between CLI and web
- **Multi-backend**: keep a profile per environment, switch with one command
- **Web shell = same account, same powers**: login, streaming chat, markdown,
  build tracking, dashboards, auto-rendered run forms, run timelines with
  artifact downloads

## The backend it talks to

guanjia is a **thin client** — it runs no model and stores no business data.
Everything (builder agent, workflow runtime, scheduler, audit ledger, users)
comes from a workflow backend you deploy yourself. That trade buys two things:
complete audit trails, and a client that cannot fake results.

The cost, stated plainly: **there is no hosted version; you need a backend first.**

**Someone already running one?** Ask them for two things:

```
server address   (e.g. https://workflow.your-company.com)
register token   (shared by the team, for self-service signup)
```

Then `guanjia --login` — pick your own username and password.
**The first person to register becomes the admin.**

**Rolling your own?** The backend needs to expose these HTTP endpoints
(they are all guanjia depends on):

| Purpose | Endpoints |
| --- | --- |
| Identity | `POST /api/v1/auth/register` · `POST /api/v1/auth/login` · `GET /api/v1/me` |
| Chat | `POST /api/v1/assistant/agent` (plus `/stream` for SSE) |
| Workflows | `GET /api/v1/applications` · `/{id}/draft` · `/{id}/runs` · `POST /{id}/runs` |
| Builds | `POST /{id}/builds` · `GET /api/v1/builds/{id}` · `POST /{id}/resume` |
| Ops | `GET /api/v1/overview` · `/api/v1/health-report` · `/api/v1/scheduler/health` |

Backends that also serve `/health-report`, `/scheduler/health`, run artifacts and
the bounded event list let guanjia show more; **older backends degrade silently
rather than erroring out** — see [known limits](docs/known-limits.md).

The reference implementation is a self-hosted FastAPI + SQLite platform
(the builder agent drives DeepSeek or any OpenAI-compatible model, local vLLM
included). Open an issue if you want a ready-made deployment — that part is
being packaged for independent release.

## Finding what broke — and fixing it

**Health check**: `guanjia doctor` names the workflows that are broken (all runs
failed in the window, or a recent failure streak) or stalled (scheduled but never
ran), each with the reason from its last failure. It also calls out the ones that
were **published but have never run** — they are not broken, but nothing yet shows
they work, and "all healthy" cannot carry them. The same report shows up in
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
Workflow backend (yours to deploy): builder agent · runtime · scheduler ·
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

MIT License. · [中文 README](README.md) · [alternatives](docs/alternatives.md) · [known limits](docs/known-limits.md)
