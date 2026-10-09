# nk-git-guardrail-hook

A [Claude Code](https://code.claude.com) skill. A PreToolUse hook for Claude Code that stops before seven risky git and shell commands — force push, git add -A in a shared checkout, making a repo public, pushing while behind the remote, a push that records a mass deletion, a recursive rm on the home folder or the filesystem root, a download run straight in a shell.

**What you get.** One real run of nk-git-guardrail-hook 0.1.8, copied from the terminal on 2026-10-09:

```text
$ python3 scripts/replay.py --demo
An invented history: Sam, the shop repository and every command below are made up for this demo.

Sam's last 30 days in Claude Code: 148 shell commands, 43 of them the kind a rule reads.
Run through the hook today, it would have stepped in on 21.

      1  force pushes: asked first
         e.g.  git push --force origin main
     13  git add -A, git add . or --all (everything in the folder staged at once): refused, with the fix
         e.g.  git add .
      0  commands that make a repository public
      6  pushes from a branch that is behind its remote, as of your last fetch: asked first
         e.g.  git push
      0  pushes that delete most of a repository, as of your last fetch
      0  recursive rm on the home folder, the filesystem root or the current folder
      1  downloads run straight in a shell (curl | sh): asked first
         e.g.  curl -fsSL https://example.com/install.sh | sh

The two push lines are judged on what is already on your disk: each repository as it is now, against its remote as
of your last fetch. Nothing was fetched, so a repository you have not fetched lately can be further behind than this says.
--fetch asks the remotes first: one `git fetch` of the current branch in each repository a past push names (1 repository here).
The other five are judged on the command itself. Nothing was pushed, committed or changed in a working tree.
$ python3 scripts/guardrail.py --try "git push --force-with-lease"
allow	
$ python3 scripts/guardrail.py --try "git push origin +main"
ask	⛔ force push. Incident: a shared branch's history was rewritten while another session was working on it; dangling commits had to be recovered by hand. If you are behind, rebase instead. Sure this is not that case?
$ python3 scripts/guardrail.py --try "gh repo edit me/app --visibility=public"
ask	🚨 this makes a repository public. Incident: an internal document went public because nobody was asked. Publishing publishes the whole history. Has a human seen the content and said yes?
$ python3 scripts/guardrail.py --try "rm -rf ~"
ask	⛔ recursive rm on ~: that is your home folder. It cannot be undone and nothing goes to a trash. Name the exact sub-folder you mean.
$ python3 scripts/guardrail.py --try "git add -A"
deny	⛔ git add -A / . / --all. Incident: with several sessions in one checkout it swept another session's half-written untracked files into this commit. Use `git add -- <named paths>`; run `git status --porcelain` first if unsure.
```

![nk-git-guardrail-hook](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/social/nk-git-guardrail-hook.png)

Part of [nickkk-skills](https://github.com/NickkkLian/nickkk-skills) — skills that stop an AI coding agent's
"done, tested, safe" from being taken on faith.

## Try it

Nothing is installed and nothing under `~/.claude` changes: clone, run the self-test, run the example.

```bash
git clone https://github.com/NickkkLian/nk-git-guardrail-hook && cd nk-git-guardrail-hook
python3 scripts/guardrail.py --selftest
python3 scripts/replay.py --selftest
python3 scripts/replay.py --demo
python3 scripts/guardrail.py --try "git push --force-with-lease"
python3 scripts/guardrail.py --try "git push origin +main"
python3 scripts/guardrail.py --try "gh repo edit me/app --visibility=public"
python3 scripts/guardrail.py --try "rm -rf ~"
python3 scripts/guardrail.py --try "git add -A"
```

The self-tests print:

```text
✔ guardrail selftest: 110 samples (ask 58 / deny 14 / allow 38) · 7 of 7 rules on with no config file
replay selftest · 17/17 passed
```

The last command prints the block at the top of this page; its last line is the one below, and its exit code is 0.

```text
deny	⛔ git add -A / . / --all. Incident: with several sessions in one checkout it swept another session's half-written untracked files into this commit. Use `git add -- <named paths>`; run `git status --porcelain` first if unsure.
```

![nk-git-guardrail-hook demo: before and after](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/nk-git-guardrail-hook.gif)

The demo above is a rendering of an earlier run and cuts its longest lines short; the block at the top of this page is a full run of this version.

## What it does

- Seven rules, all on with no config file — force push (`--force`, `-f` or a `+` refspec such as `+main`), `git add -A`, repo → public (`--public`, `--visibility public` or `--visibility=public`), push while behind, push that mass-deletes, a recursive `rm` on the home folder, the filesystem root or the current folder, and a download run in a shell (`curl | sh` or `sh -c "$(curl …)"`). The first five name, in the prompt, the incident behind the rule; the last two say why the step is irreversible or dangerous.
- A config file is only for extras: your own project folders for the `rm` rule, and the thresholds.
- Ask by default; deny only where the agent can fix its own command; fail-open when the hook breaks.
- `replay.py --summary` is the first look, before you install anything: one screen that says, for each rule, how many of your own shell commands from the last 30 days the hook would have refused or asked about, with one of those commands as an example and a plain 0 where the rule never fired. It reaches no network: the two push rules are judged against each remote as of your last fetch, and the screen says so. `--summary --fetch` asks the remotes first (one `git fetch` of the current branch in each repository a past push names). `--demo` prints the same screen from an invented history and reads nothing of yours.
- `replay.py` without `--summary` prints the full allow, ask and deny distribution with samples, so a rule is tuned on evidence.
- `--try "<command>"` shows the decision; `--selftest` runs 110 samples through the real entry point, seven of them against real temporary repositories, and ends by counting the rules that answered with no config file (7 of 7).

The full procedure, the boundaries and where the rules came from are in [SKILL.md](SKILL.md).

## Next to cc-safety-net and permissions.deny

[cc-safety-net](https://github.com/kenryu42/claude-code-safety-net) is the better-known hook for this job and covers more:
its blocked-commands list (read 2026-09-30) includes `git reset --hard`, `git clean -f`, `git checkout -- <files>`, `git branch -D`,
`rm -rf` outside the working directory and `find -delete`, and it supports more agents than Claude Code. This hook blocks none of
those four git commands, and its `rm` rule is narrower: with no config it asks only about the home folder, the filesystem root, a
folder above home and the current folder. What it has, and that list does not: a push while the branch is behind origin (it runs a real fetch), a push
whose pending commits delete most of a repository, `git add -A`, and making a repository public; and its prompts carry the incident
behind the rule. cc-safety-net was read, not installed or run here. `permissions.deny` in settings.json blocks a command pattern
outright; it cannot look at the repository, so it cannot tell a normal push from one that deletes 1,000 files. The three can run side by side.

## How it works

1. Ask, not deny — except where the fix belongs to the agent.
2. Fail-open. Any internal error → exit 0, no output.
3. Five rules cite an incident; two say why they exist.
4. Heredoc bodies are data, unless a shell consumes them (`bash <<EOF`, `… | sh`, `eval`, `ssh host <<EOF`).
5. Same-segment only. A rule looks at its own command segment (up to `;`, `&&`, `|`, newline); a path in the next command is not blamed on this `rm`.

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

Standard library only, Python 3.9+, and git. On 2026-10-09 every self-test above passed, and
`breakcheck.py` from [nk-breakable-selftest](https://github.com/NickkkLian/nk-breakable-selftest) broke each script on purpose in a sandbox copy:

- `guardrail.py`: 18 hand-written breaks (one per rule, one for each form added in 0.1.5 and 0.1.6, and one that makes rule 6 depend on a config file again); each turned the self-test red without a traceback.
- `replay.py`: 13 hand-written breaks (one for each self-test case of the summary); each turned the self-test red without a traceback.

The unmutated control stayed green every time. Only lines that record a finding, raise, or return a failing exit code
were broken (the tool's pattern, or the hand-written list); a line number refers to the script as shipped in this version.
This shows those lines are covered. It does not show that nothing else can fail.

## Limits

- Seven rules, not a full safety net. `git reset --hard`, `git clean -f`, `git checkout -- .` and `git branch -D` are allowed: none has an incident behind it here. [cc-safety-net](https://github.com/kenryu42/claude-code-safety-net) blocks those and many more, for more agents; the two can run side by side.
- Rule 6 asks about four targets with no config: the home folder, the filesystem root, a folder above home, and `.` or `..`. It does not ask about a folder inside home (`~/Documents`), a bare `*` in an ordinary folder, or a project folder, unless `protected_roots` names it. cc-safety-net asks about every recursive `rm` outside the working directory.
- Only Bash. A malicious file written with an editor tool and run some other way is not seen.
- Targets passed through variables other than `$HOME` and `$PWD` (`R=~/projects/app; rm -rf $R`) and heredoc bodies fed to python/node that shell out. Real isolation is a sandbox; this hook removes the most common step.
- It reads the command, not the files the command runs. A download saved first and run second (`curl -o i.sh …; sh i.sh`) is two ordinary commands to it, and `python3 -c "$(curl …)"` is not matched (only the shell forms are).
- Deleting by other means is not seen: `find ~ -delete`, `xargs rm`, a `cd` in an earlier command of the session.
- `replay.py --summary` counts what the hook says today. A push that was behind its remote last week and has been pulled since counts as 0; a command whose folder is gone is judged in the folder you run the summary from. Without `--fetch` it knows each remote only as of your last fetch.
- The full replay (`replay.py` without `--summary`) goes through the hook's real entry point, so it runs the hook's `git fetch` for every past push it replays, as it did before 0.1.8.

## Privacy

This hook runs on your computer: Claude Code starts it before each shell command. It reads the command about to run and the folder it runs in, plus your config file if you made one, and answers allow, ask or deny; the hook itself writes no file and keeps nothing. Before a `git push` it asks git about that repository (how far behind it is, how many files the push deletes) and runs `git fetch` for the current branch, so git contacts the repository's own remote and updates its local record of that branch, as a fetch always does; nothing else leaves your computer through the hook. The bundled `replay.py` runs only when you start it: it reads your Claude Code session transcripts under `~/.claude/projects`, puts the shell commands in them through the hook, prints counts and sample commands, and writes a file only with `--out`. Its `--summary` screen contacts no remote unless you add `--fetch`; with `--fetch`, and in the full replay, a past `git push` triggers the same fetch. Questions: open an issue on this repository.

## License

MIT. Read a script before letting it run in your environment.
