# nk-git-guardrail-hook

A [Claude Code](https://code.claude.com) skill. A PreToolUse hook for Claude Code that stops before the git and shell commands that have actually destroyed work — force push, git add -A in a shared checkout, making a repo public, pushing while behind the remote, a push that records a mass deletion, rm -rf on a project root, curl piped into a shell — and names the incident in the prompt.

Part of [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) — skills that stop an AI coding agent's
"done, tested, safe" from being taken on faith.

## What it does

- Seven rules — force push, `git add -A`, repo → public, push while behind, push that mass-deletes, `rm -rf` on a project root, `curl | sh` — each with its incident in the prompt.
- Ask by default; deny only where the agent can fix its own command; fail-open when the hook breaks.
- `replay.py` runs your real command history through the hook so rules are tuned on evidence.
- `--try "<command>"` shows the decision; `--selftest` runs 39 samples through the real entry point.

The full procedure, the boundaries and where the rules came from are in [SKILL.md](SKILL.md).

## Install

Copy the folder into your skills directory (the skill is the repository root):

```bash
git clone https://github.com/NickkkLian/nk-git-guardrail-hook ~/.claude/skills/nk-git-guardrail-hook
```

or inside one project: `git clone … .claude/skills/nk-git-guardrail-hook`.

As a plugin, through the marketplace in the index repository:

```
/plugin marketplace add NickkkLian/nickkk-skills
/plugin install nk-git-guardrail-hook@nickkk-skills
```

To try it for one session without installing: `claude --plugin-dir ./nk-git-guardrail-hook`.

## Verify

```bash
python3 scripts/guardrail.py --selftest
python3 scripts/replay.py --selftest
```

Standard library only, Python 3.9+. Before publishing, the guarded lines of each script were
mutated one at a time in a sandbox copy and the self-test was confirmed to go red on the named
assertion, without a traceback; the unmutated control stayed green.

## License

MIT. Read a script before letting it run in your environment.
