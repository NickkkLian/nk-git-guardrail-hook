# nk-git-guardrail-hook

![nk-git-guardrail-hook](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/social/nk-git-guardrail-hook.png)

A [Claude Code](https://code.claude.com) skill. A PreToolUse hook for Claude Code that stops before seven risky git and shell commands — force push, git add -A in a shared checkout, making a repo public, pushing while behind the remote, a push that records a mass deletion, rm -rf on a project root, curl piped into a shell.

Part of [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) — skills that stop an AI coding agent's
"done, tested, safe" from being taken on faith.

![nk-git-guardrail-hook demo: before and after](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/nk-git-guardrail-hook.gif)

## What it does

- Seven rules — force push, `git add -A`, repo → public, push while behind, push that mass-deletes, `rm -rf` on a project root, `curl | sh`. The first five name, in the prompt, the incident behind the rule; the last two say why the step is irreversible or dangerous.
- Ask by default; deny only where the agent can fix its own command; fail-open when the hook breaks.
- `replay.py` runs your real command history through the hook so rules are tuned on evidence.
- `--try "<command>"` shows the decision; `--selftest` runs 39 samples through the real entry point.

The full procedure, the boundaries and where the rules came from are in [SKILL.md](SKILL.md).

## How it works

1. Ask, not deny
2. Fail-open
3. Five rules cite an incident; two say why they exist
4. Heredoc bodies are data
5. Same-segment only

## Why it is built this way

**The idea.** A red line that lives in a document is enforced by whoever happens to remember it. This hook moves seven of them into the one place every Bash command passes through, and its prompt says what is at stake: rules 1–5 name the real incident behind them; rules 6 and 7 have no recorded incident, and their prompts say why the step is irreversible or dangerous.

**Where it came from.** Started as six rules after a review of the author's own setup found enforcement to be its thinnest part — many red lines, nothing enforcing them.

**Evidence.** What was broken on purpose to show that the self-tests can fail is under [Verify](#verify); what was run end to end, and in which agent, is under [Compatibility](#compatibility).

## Install

Pick one of four ways: three for Claude Code, one for OpenAI Codex. Skills load when a session starts, so open a **new** session after installing.

### 1 · Terminal, one command

```bash
git clone https://github.com/NickkkLian/nk-git-guardrail-hook ~/.claude/skills/nk-git-guardrail-hook
```

1. Run the command above (for one project only, clone into `.claude/skills/nk-git-guardrail-hook` inside that project).
2. Start a new Claude Code session.
3. Check it loaded: type `/nk-git-guardrail-hook` — it appears in the slash-command menu. Or just ask for the task; the skill triggers on its own.

### 2 · Claude Code in a terminal session (plugin)

The plugin route goes through the [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) marketplace. Add it once; after that each skill is one command.

```
/plugin marketplace add NickkkLian/nickkk-skills
/plugin install nk-git-guardrail-hook@nickkk-skills
```

1. In a Claude Code session, run the first line (once per machine).
2. Run the second line.
3. Start a new session (or run `/reload-plugins`). The skill shows up as `nk-git-guardrail-hook:nk-git-guardrail-hook`.

Without opening a session, the same two steps work from a shell: `claude plugin marketplace add NickkkLian/nickkk-skills` then `claude plugin install nk-git-guardrail-hook@nickkk-skills`.

### 3 · Claude desktop app (Code tab)

**Add the marketplace first — Discover only searches marketplaces you have already added.**

<img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/panel-route.gif" alt="Adding the marketplace and installing a skill in the desktop app" width="640">

<sub>Recorded on 2026-09-16, when the marketplace listed ten skills, all at version 0.1.0; it lists more now. The repository list in this recording shows the recorder's own repositories because a GitHub account is connected; yours will show yours. Type the full name as in step 4.</sub>

1. In the chat box, type `/plugin marketplace` and press Enter (or open **Settings → Customize → Plugins**). The **Plugins** panel opens.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step1-type-plugin-marketplace.png" alt="/plugin marketplace typed in the chat box" width="480">
2. Top right, open **Add ▾** and choose **Add marketplace**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step2-add-menu.png" alt="The Add menu with Add marketplace" width="480">
3. Choose **Add from a repository**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step3-add-from-repository.png" alt="Add marketplace dialog: Add from a repository" width="480">
4. In **URL**, type the full `NickkkLian/nickkk-skills`. At the bottom of the list choose the row **Use "NickkkLian/nickkk-skills"**, then press **Sync**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step4-url-then-sync.png" alt="URL filled in, Sync button" width="480">
5. You land on **Discover**, filtered to the new marketplace (**Filter · 1**). Find **Nk git guardrail hook** and press **Add**. Installed ones show **✓ Added**.
   <br><img src="https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/panel-route/step5-discover-add.png" alt="Discover list with Added and Add buttons" width="480">
6. Close the panel and start a new session.

To try it for one session without installing anything: `claude --plugin-dir ./nk-git-guardrail-hook` from a clone.

### 4 · OpenAI Codex CLI

```bash
git clone https://github.com/NickkkLian/nk-git-guardrail-hook.git ~/.agents/skills/nk-git-guardrail-hook
```

1. Run the command above (for one project only, clone into `.agents/skills/nk-git-guardrail-hook` inside that project).
2. Start a new Codex session.
3. Check it loaded, without spending a model call: `codex debug prompt-input | grep -o -- '- nk-git-guardrail-hook[a-z0-9:-]*' | sort -u` prints `- nk-git-guardrail-hook:nk-git-guardrail-hook:`. Codex adds the `nk-git-guardrail-hook:` prefix because this repository also carries a Claude Code plugin manifest. Ask for the task and the skill triggers on its own, or type `$` and pick it from the list.

## Compatibility

| Agent | Tested | What was checked |
|---|---|---|
| Claude Code (CLI 2.1.173, macOS) | yes | In a fresh project with an isolated Claude config, inside a macOS sandbox that blocked reading the tester's ~/.claude folder (settings, session history, memory), Desktop, Documents and Downloads, SSH keys and git identity, a plain request that never names the skill triggered it and it ran its bundled script. The route 2 plugin commands were also run from a shell with an isolated config: marketplace add, install, list. Here it tried to put the hook in the user-level settings file, which the test session was not allowed to write, so it showed the exact settings block and ran the force-push case through the hook's `--try`: it stops and asks. |
| OpenAI Codex CLI (0.154.0-alpha.6.2, gpt-5.6-sol, low reasoning, macOS) | partly | Copied into `~/.agents/skills` of a temporary home (the folder route 4 clones into), in a fresh project, without the user's Codex config. From a plain request that never names the skill, Codex read SKILL.md, wrote the hook into `.claude/settings.json`, ran the 39-case self-test and showed that a force push would stop and ask. That hook is written for Claude Code sessions; whether it also guards Codex sessions was not tested. |
| Cursor, Gemini CLI | no | Not tested. Their documentation says both read `~/.agents/skills`, the folder route 4 clones into; Gemini CLI asks before it activates a skill. |

In this skill's Codex run, every call into the skill folder's scripts/ used that folder's absolute path. Route 4 was checked for this repository: cloned from GitHub into a temporary home's `~/.agents/skills`, it was listed by the step 3 command. This skill's frontmatter uses only name, description, license and metadata.

## Verify

```bash
python3 scripts/guardrail.py --selftest
python3 scripts/replay.py --selftest
```

Standard library only, Python 3.9+. Before publishing, the guarded lines of each script were
mutated one at a time in a sandbox copy and the self-test was confirmed to go red on the named
assertion, without a traceback; the unmutated control stayed green.

## Limits

- Only Bash. A malicious file written with an editor tool and run some other way is not seen.
- Targets passed through variables (`R=~/projects/app; rm -rf $R`) and heredoc bodies fed to python/node that shell out. Real isolation is a sandbox; this hook removes the most common step.
- It reads the command, not the files the command runs.

## License

MIT. Read a script before letting it run in your environment.
