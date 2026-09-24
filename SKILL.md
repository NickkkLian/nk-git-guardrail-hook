---
name: nk-git-guardrail-hook
description: A PreToolUse hook for Claude Code that stops before seven risky git and shell commands — force push, git add -A in a shared checkout, making a repo public, pushing while behind the remote, a push that records a mass deletion, rm -rf on a project root, curl piped into a shell. The prompt says what is at stake: for the first five, the real incident behind the rule; for the last two, why the step is irreversible or dangerous. Use when several agent sessions share a machine, when an agent pushes on your behalf, or when you keep clicking through the same confirmation (then replay real command history to narrow or harden the rule). Ask by default, deny only where the agent can fix its own command, fail-open if the hook itself breaks.
license: MIT
metadata:
  provenance: own practice (2026-08 to 2026-09); no external source
  version: 0.1.3
---
# Git guardrail hook

**A red line that lives in a document is enforced by whoever happens to remember it.** This hook moves seven
of them into the one place every Bash command passes through, and its prompt says what is at stake: rules 1–5
name the real incident behind them; rules 6 and 7 have no recorded incident, and their prompts say why the step
is irreversible or dangerous.

> **Paths.** Commands in this skill start with `${…SKILL_DIR}`: this skill's own folder, the one that contains this SKILL.md. Claude Code fills it in. If your agent shows the placeholder as written (Codex, Cursor, Gemini CLI and others), replace it with that folder's absolute path before you run the command. Left as it is, it expands to nothing and the path breaks.

## Install (two minutes)

1. Copy the skill; then print the settings snippet and merge it into `~/.claude/settings.json`:
   `python3 ${CLAUDE_SKILL_DIR}/scripts/guardrail.py --settings-snippet`
2. Optional config at `~/.config/guardrail/config.json`:
   `{"protected_roots": ["~/projects"], "add_all": "deny", "mass_delete_min": 20, "mass_delete_ratio": 3}`
   `protected_roots` turns on the `rm -rf` rule for project-level paths under those roots.
3. Restart the session (hooks load at start). Check it is live: `python3 ${CLAUDE_SKILL_DIR}/scripts/guardrail.py --try "git push --force"` prints `ask` and the reason.
4. Run the self-test once: `python3 ${CLAUDE_SKILL_DIR}/scripts/guardrail.py --selftest` (39 commands through the real entry point; ask, deny and allow each have samples).

## The rules

| # | Command shape | Decision | Why it exists |
|---|---|---|---|
| 1 | `git push --force` / `-f` / `+ref` (not `--force-with-lease`) | ask | incident: a shared branch's history rewritten while another session was rebasing onto it |
| 2 | `git add -A` / `.` / `--all` / `*` / `./` / `:/` | deny (configurable) | incident: with several sessions in one checkout, another session's half-written files were swept into a commit |
| 3 | `gh repo create/edit --public`, `gh api … private=false` | ask | incident: an internal page went public because nobody was asked; publishing publishes all history |
| 4 | `git push` while the branch is behind origin (a real `fetch` is run) | ask | incident: a stale local copy was built and deployed over work that only existed on the remote |
| 5 | `git push` whose pending commits delete ≥ 20 files and 3× more than they add (cumulative since origin) | ask | incident: an interrupted sparse clone left an empty worktree; the commit recorded 1,000+ deletions; add/commit/push all exited 0 |
| 6 | `rm -rf` on a path ≤ 2 levels under a protected root | ask | no recorded incident: the step is irreversible; scratch dirs and temp clones are deliberately not protected |
| 7 | `curl`/`wget` piped into `sh`/`bash`/`python3`/`node`… | ask | no recorded incident: it runs downloaded code nobody has read, the closing step of an "install script" attack chain; save it, read it, report it |

Rules 4 and 5 resolve the repository the command acts on (`git -C <path>` > last `cd` > cwd), because the
incident behind rule 5 happened in a temporary clone, exactly where a cwd-based check is blind.

## Design rules (why it is built this way)

- **Ask, not deny** — except where the fix belongs to the agent. `git add -A` is denied with the fix in the
  reason (`git add -- <paths>`) because a human clicking "allow" 169 times in a week is a cost moved to the
  wrong person; the agent can correct its own command.
- **Fail-open.** Any internal error → exit 0, no output. A guardrail that blocks every command is worse
  than none. (Detectors are the opposite: they must fail loud. Know which one you are writing.)
- **Five rules cite an incident; two say why they exist.** Rules were meant to come only from incidents,
  because imagined risks produce false positives, and a few false positives teach people to click through
  everything. `rm -rf` on a project root and `curl | sh` are the exceptions: neither has a recorded incident,
  and their prompts say what is at stake instead — `rm -rf` cannot be undone; `curl | sh` runs code nobody has read.
- **Heredoc bodies are data**, unless a shell consumes them (`bash <<EOF`, `… | sh`, `eval`, `ssh host <<EOF`).
  Quoted strings are ignored, but `$(…)` inside quotes is kept — it runs.
- **Same-segment only.** A rule looks at its own command segment (up to `;`, `&&`, `|`, newline); a path in
  the next command is not blamed on this `rm`. The price: a target passed through a variable is invisible.

## Tuning with real history

When the same prompt keeps appearing: `python3 ${CLAUDE_SKILL_DIR}/scripts/replay.py --days 7` feeds every
Bash command your sessions ran (subagents included) through the hook and prints the decision distribution
with samples per reason. Run it before and after a rule change; the diff is the evidence. Two outcomes:
false positives → narrow the rule; true positives that the agent can fix itself → deny with the fix in the
reason. The only prompts worth keeping are the ones a human should actually decide.

## Boundaries (what it cannot see)

- Only Bash. A malicious file written with an editor tool and run some other way is not seen.
- Targets passed through variables (`R=~/projects/app; rm -rf $R`) and heredoc bodies fed to
  python/node that shell out. Real isolation is a sandbox; this hook removes the most common step.
- It reads the command, not the files the command runs.

## Provenance

Own practice, 2026-08 to 2026-09. Started as six rules after a review of the author's own setup found
enforcement to be its thinnest part — many red lines, nothing enforcing them. Rules were then narrowed or hardened using a
seven-day replay of real command history (about 7,500 commands): one rule went from ask to deny after
169 prompts with no true positive; a rule with no incident behind it was removed, and another was cut
down to its `curl | sh` line, kept as rule 7 without an incident. No external source.
