# nk-git-guardrail-hook

A [Claude Code](https://code.claude.com) skill. A PreToolUse hook for Claude Code that stops before seven risky git and shell commands — force push, git add -A in a shared checkout, making a repo public, pushing while behind the remote, a push that records a mass deletion, a recursive rm on the home folder or the filesystem root, a download run straight in a shell.

**What you get.** Deleting every file and committing exits 0, and nothing in git stops the push that follows. The hook counts what that push would delete and asks first. A real run of 0.1.9 on a test repository with 40 files, 2026-10-14:

```text
$ git rm -rq src && git commit -qm "sync"; echo "exit $?"
exit 0
$ git diff --shortstat origin/main...HEAD
 40 files changed, 40 deletions(-)
$ python3 ../nk-git-guardrail-hook/scripts/guardrail.py --try "git push origin main"
ask  🚨 this push deletes 40 files (adds/modifies only 0). Incident: an interrupted sparse clone left an empty worktree, the commit recorded every file as deleted, and add/commit/push all exited 0. Check `git diff --cached --name-status | grep '^D'`; count the remote with `git ls-tree -r --name-only origin/<branch> | wc -l`, not `ls`. Source main → origin/main.
```

![nk-git-guardrail-hook 0.1.9 on a test repository with 40 files: git rm and git commit exit 0, the diff says 40 files changed, 40 deletions, and the hook answers ask: this push deletes 40 files](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/results/nk-git-guardrail-hook-mass-deletion.png)

The three lines that build that repository are under [Try it](#try-it). `--try` prints the answer the hook would give for a command and does not run the command. Installed as a hook, `ask` stops the push before it runs. An interactive session shows you that text and waits for your answer; a non-interactive one (`claude -p`) refuses the push and hands the text back to the agent. The picture is the same run drawn from its text, not Claude Code's own dialog.

Three of its seven rules. The first two look at the repository, not at the command: `git push origin main` is the same text whether it deletes 0 files or 40. Each one asks before the command runs:

- **A push that deletes most of a repository**: 20 or more files gone, and over three times what the unpushed commits add or change.
- **A push of a branch that is behind its destination on the remote**: it fetches that branch first, then counts the commits you do not have.
- **A command that makes a repository public**: `gh repo create --public`, `gh repo edit --visibility public`, or the same through `gh api`.

**How the two push rules were measured (0.1.9).** 1,008 test lines, each run in a throwaway repository with local remotes; git's own `git push --dry-run` said what each push would send. On the 605 lines where git would send a risky push (one that deletes most of the files, or a branch behind the remote), 0.1.8 let 481 through and 0.1.9 lets 27 through, all of them files removed in ways listed under [Limits](#limits). 0.1.9 asks with a count on 341 of them (0.1.8: 124) and asks as "not judged" on 237. On the 311 lines where the push is harmless, 0.1.9 stays silent on 285 and stops on 26 (0.1.8: 12), 20 of them as "not judged". The lines were written by AI agents that did not write the fix; a second agent ran all of them again on 2026-10-14 and got the same answer on every line. No real remote was used.

[cc-safety-net](https://github.com/kenryu42/claude-code-safety-net), a better-known hook, blocks more commands than this one; its blocked-commands page, as read on 2026-09-30, lists none of these three. Its code was not read, it was not installed or run, and no other hook was compared: see [Next to cc-safety-net and permissions.deny](#next-to-cc-safety-net-and-permissionsdeny).

**The author's own 30 days.** `replay.py --summary` of 0.1.9 on the author's Claude Code history, 2026-10-14: of 67,467 shell commands, the hook would have stepped in on 224. 0.1.8, run on the same history at the same time, would have stepped in on 123 of 67,467, so 0.1.9 steps in about 1.8 times as often. Most of the difference is the pushes 0.1.9 could not work out and asks about as "not judged": 109, 33 of them because the folder is written as a shell expansion (`git -C "$DIR" push`, `cd "$DIR" && git push`), which the hook does not resolve; 0.1.8 had no such answer. The rest: 71 `git add -A` or `git add .` (a house rule for a checkout that several sessions share; 0.1.8: 71), 10 pushes from a branch behind its remote (0.1.8: 18), 28 downloads run straight in a shell (0.1.8: 28), 6 force pushes (0.1.8: 6), and no mass-deletion push in either count. The push counts judge each repository as it is today against its remote as of its last fetch, not as it was when the push happened, so read them as rough. The same command counts your own history before you install anything.

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

After its first line, `guardrail.py --selftest` runs eight push lines against temporary repositories and prints its time (under 16 seconds on the two Python versions tried). `python3 scripts/guardrail.py --selftest-full` runs every push case in the four test files next to it and takes several minutes. The first `--try` line below is a push: for a push, `--try` looks at the clone's remote the way the hook does before a real push.

The example commands print this (0.1.9, copied from the terminal on 2026-10-14; every command exits 0). The first screen is `--demo`: Sam, the shop repository and every command on it are invented, and nothing of yours is read. `python3 scripts/replay.py --summary` prints the same screen from your own last 30 days.

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
--fetch asks the remotes first: read each selected remote's ref names, then fetch only the compared destinations (1 repository here).
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

To repeat the run at the top of this page, build the test repository with these three lines, then run the three commands of that block inside it:

```bash
# next to your clone of nk-git-guardrail-hook
git init -q --bare remote.git && git clone -q remote.git test-repo && cd test-repo
git checkout -q -B main && mkdir src && for i in $(seq 40); do echo $i > src/$i.txt; done
git add -- src && git commit -qm "40 files" && git push -q -u origin main
```

![nk-git-guardrail-hook demo: before and after](https://raw.githubusercontent.com/NickkkLian/nickkk-skills/main/gallery/nk-git-guardrail-hook.gif)

The demo above is a rendering of an earlier run and cuts its longest lines short; the block under [Try it](#try-it) is a full run of this version.

## What it does

- Seven rules, all on with no config file — force push (`--force`, `-f` or a `+` refspec such as `+main`), `git add -A`, repo → public (`--public`, `--visibility public` or `--visibility=public`), push while behind, push that mass-deletes, a recursive `rm` on the home folder, the filesystem root or the current folder, and a download run in a shell (`curl | sh` or `sh -c "$(curl …)"`). The first five name, in the prompt, the incident behind the rule; the last two say why the step is irreversible or dangerous.
- A config file is only for extras: your own project folders for the `rm` rule, and the thresholds.
- Ask by default; deny only where the agent can fix its own command; fail-open when the hook breaks.
- `replay.py --summary` is the first look, before you install anything: one screen that says, for each rule, how many of your own shell commands from the last 30 days the hook would have refused or asked about, with one of those commands as an example and a plain 0 where the rule never fired. It reaches no network: the two push rules are judged against each remote as of your last fetch, and the screen says so. `--summary --fetch` asks the remotes first (one remote-name lookup per selected remote in each repository a past push names, then one narrow fetch per compared destination). Not-judged asks are counted once and split by reason; missing recorded or resolved folders are reported separately as unable to replay. `--demo` prints the same screen from an invented history and reads nothing of yours.
- `replay.py` without `--summary` prints the full allow, ask and deny distribution with samples, so a rule is tuned on evidence.
- `--try "<command>"` shows the decision; `--selftest` runs the original 110 samples plus eight quick push-line checks (it prints its time). `--selftest-full` adds all push/projection/review regressions and the hanging-child case; allow several minutes. All seven rules are demonstrated without a config file.

The full procedure, the boundaries and where the rules came from are in [SKILL.md](SKILL.md).

## Next to cc-safety-net and permissions.deny

[cc-safety-net](https://github.com/kenryu42/claude-code-safety-net) is a better-known hook for this job and covers more:
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
5. Same-segment only, except the two push rules. The other five look at their own command segment (up to `;`, `&&`, `|`, newline); a path in the next command is not blamed on this `rm`. The two push rules read the whole line up to the push.

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
python3 scripts/push_line_selftest.py --selftest
python3 scripts/push_review_selftest.py --selftest
python3 scripts/push_selftest.py --selftest
python3 scripts/push_work_selftest.py --selftest
python3 scripts/replay.py --selftest
```

Standard library only, Python 3.9+, and git. On 2026-10-14 every self-test above passed, and
`breakcheck.py` from [nk-breakable-selftest](https://github.com/NickkkLian/nk-breakable-selftest) broke each script on purpose in a sandbox copy:

- `guardrail.py`: 18 hand-written breaks (one per rule, one for each form added in 0.1.5 and 0.1.6, and one that makes rule 6 depend on a config file again); 16 turned the self-test red without a traceback. Not covered: the self-test stayed green with rule 1 force push, rule 1 without the + refspec form switched off (a second force-push check, for a resolved argument or alias, still asks when either is switched off, so these two breaks do not show the self-test is blind there).
- `push_line_selftest.py`: no break run. It is a test file, the cases that `guardrail.py --selftest-full` runs; nothing in it was broken on purpose.
- `push_review_selftest.py`: no break run. It is a test file, the cases that `guardrail.py --selftest-full` runs; nothing in it was broken on purpose.
- `push_selftest.py`: no break run. It is a test file, the cases that `guardrail.py --selftest-full` runs; nothing in it was broken on purpose.
- `push_work_selftest.py`: no break run. It is a test file, the cases that `guardrail.py --selftest-full` runs; nothing in it was broken on purpose.
- `replay.py`: 13 hand-written breaks (one for each self-test case of the summary); each turned the self-test red without a traceback.

The unmutated control stayed green every time. Only lines that record a finding, raise, or return a failing exit code
were broken (the tool's pattern, or the hand-written list); a line number refers to the script as shipped in this version.
This shows those lines are covered. It does not show that nothing else can fail.

## Limits

- Seven rules, not a full safety net. `git reset --hard`, `git clean -f`, `git checkout -- .` and `git branch -D` are allowed: none has an incident behind it here. [cc-safety-net](https://github.com/kenryu42/claude-code-safety-net) blocks those and many more, for more agents; the two can run side by side.
- Rule 6 asks about four targets with no config: the home folder, the filesystem root, a folder above home, and `.` or `..`. It does not ask about a folder inside home (`~/Documents`), a bare `*` in an ordinary folder, or a project folder, unless `protected_roots` names it. cc-safety-net asks about every recursive `rm` outside the working directory.
- The two push rules (behind the remote, mass deletion) in 0.1.9, in short. They judge the branch the push would send against the branch it would update, and they read the rest of the command line for a commit and for files removed before it. Where they cannot work the push out (an address that matches no configured remote, a commit id as the source, an earlier `git pull` or `git merge` not joined to the push by `&&`, a folder written as a shell expansion), they ask and say "not judged" instead of giving a count. A push that is itself hidden behind `eval`, a variable, `$(which git)` or text piped into a shell is asked about the same way. A wipe can still pass silently when the files are removed before the commit by something the hook does not simulate: a script (`python3 -c`, `perl -e`), another program (`mv`, `trash`), Git plumbing (`git read-tree`, `git update-index --force-remove`), an `rm` behind `eval`, a variable, `bash -c`, `sh -c` (also through `find -exec` or `xargs`), `env -S`, `env -C` or an unknown wrapper such as `doas`, or a target written with braces or in different letter case. A target reached through a symbolic link was not tested on this version. The supported forms, one by one, are in [the reference](references/settings.md#push-resolution-and-limits).
- Only Bash. A malicious file written with an editor tool and run some other way is not seen.
- Targets passed through variables other than `$HOME` and `$PWD` (`R=~/projects/app; rm -rf $R`) and heredoc bodies fed to python/node that shell out. Real isolation is a sandbox; this hook removes the most common step.
- It reads the command, not the files the command runs. A download saved first and run second (`curl -o i.sh …; sh i.sh`) is two ordinary commands to it, and `python3 -c "$(curl …)"` is not matched (only the shell forms are).
- Deleting by other means is not seen: `find ~ -delete`, `xargs rm`, a `cd` in an earlier command of the session.
- `replay.py --summary` counts what the hook says today. A push that was behind its remote last week and has been pulled since counts as 0; a command whose recorded or resolved folder is gone is reported as unable to replay. Without `--fetch` it knows each remote only as of your last fetch.
- The full replay (`replay.py` without `--summary`) goes through the hook's real entry point, so it runs the hook's fetch for each past branch push it replays.

## Privacy

This hook runs on your computer: Claude Code starts it before each shell command. It reads the command about to run and the folder it runs in, plus your config file if you made one, and answers allow, ask or deny; the hook itself writes no file and keeps nothing. Before a `git push` it asks git about that repository (how far behind the pushed branch is, how many files the push deletes), asks the remote the push names for its branch and tag names (`git ls-remote`), and runs `git fetch` for the branch the push would update (for a new branch, the remote's default branch), so git contacts that remote and updates its local record of that branch, as a fetch always does; nothing else leaves your computer through the hook. The bundled `replay.py` runs only when you start it: it reads your Claude Code session transcripts under `~/.claude/projects`, puts the shell commands in them through the hook, prints counts and sample commands, and writes a file only with `--out`. Its `--summary` screen contacts no remote unless you add `--fetch`; with `--fetch`, and in the full replay, a past `git push` triggers the same lookup and fetch. Questions: open an issue on this repository.

## License

MIT. Read a script before letting it run in your environment.
