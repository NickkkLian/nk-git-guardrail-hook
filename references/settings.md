# Wiring the hook

`~/.claude/settings.json` (merge; keep any hooks you already have):
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /absolute/path/to/nk-git-guardrail-hook/scripts/guardrail.py", "timeout": 25 }
        ]
      }
    ]
  }
}
```
`--settings-snippet` prints this with the absolute path filled in. Hooks are loaded when a session starts;
edit the script freely, but restart the session to pick up a changed *path*.

Temporarily off: remove the `hooks` block. Per-project hooks go in `.claude/settings.json` in the project.

The hook prints a JSON decision (`ask` / `deny` with `permissionDecisionReason`) or nothing (allow). It
never prints anything on its own error: fail-open is a design rule, not an oversight.
