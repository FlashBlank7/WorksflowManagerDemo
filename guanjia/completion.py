"""guanjia completion：bash/zsh 补全脚本（静态零依赖，动态项走隐藏子命令）。

    eval "$(guanjia completion bash)"     # 当场生效
    guanjia completion bash > ~/.local/share/bash-completion/completions/guanjia
    eval "$(guanjia completion zsh)"      # zsh 走 bashcompinit

动态补全：`run` 后补工作流名（guanjia _wf-names，3s 超时静默），
`remote use/rm` 后补档案名（guanjia _profile-names，纯本地）。
"""

from __future__ import annotations

import sys

BASH = r"""_guanjia_complete(){
  local cur prev
  cur="${COMP_WORDS[COMP_CWORD]}"
  prev="${COMP_WORDS[COMP_CWORD-1]}"
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=( $(compgen -W "web today remote doctor run rerun completion --login --version" -- "$cur") )
    return
  fi
  case "${COMP_WORDS[1]}" in
    remote)
      if [ "$COMP_CWORD" -eq 2 ]; then
        COMPREPLY=( $(compgen -W "list use add rm" -- "$cur") )
      elif [ "$COMP_CWORD" -eq 3 ] && { [ "$prev" = use ] || [ "$prev" = rm ]; }; then
        local IFS=$'\n'
        COMPREPLY=( $(compgen -W "$(guanjia _profile-names 2>/dev/null)" -- "$cur") )
      fi;;
    run)
      if [ "$COMP_CWORD" -eq 2 ]; then
        local IFS=$'\n'
        COMPREPLY=( $(compgen -W "$(guanjia _wf-names 2>/dev/null)" -- "$cur") )
      else
        COMPREPLY=( $(compgen -W "--json --wait" -- "$cur") )
      fi;;
    web)
      COMPREPLY=( $(compgen -W "--port --open --app --server --token" -- "$cur") );;
    completion)
      COMPREPLY=( $(compgen -W "bash zsh" -- "$cur") );;
  esac
}
complete -F _guanjia_complete guanjia
"""

ZSH_PREAMBLE = """autoload -U +X bashcompinit && bashcompinit
"""


def print_workflow_names() -> None:
    """隐藏子命令 _wf-names：已发布工作流名，一行一个；任何失败都静默。"""
    try:
        from .config import load_config
        from .plugins import workflow
        from .remote import RemoteClient

        cfg = load_config()
        if not cfg["token"]:
            return
        remote = RemoteClient(cfg["server"], cfg["token"], timeout=3.0)
        for item in workflow.list_workflows(remote):
            if item.get("published") and item.get("name"):
                print(item["name"])
    except Exception:  # noqa: BLE001 - 补全绝不打扰正常输入
        pass


def print_profile_names() -> None:
    """隐藏子命令 _profile-names：本地档案名，一行一个。"""
    try:
        from .config import list_profiles

        _, profiles = list_profiles()
        for name in profiles:
            print(name)
    except Exception:  # noqa: BLE001
        pass


def main(argv: list[str]) -> int:
    shell = argv[0] if argv else ""
    if shell == "bash":
        print(BASH)
        return 0
    if shell == "zsh":
        print(ZSH_PREAMBLE + BASH)
        return 0
    print('用法：guanjia completion bash|zsh，然后 eval "$(guanjia completion bash)"',
          file=sys.stderr)
    return 2
