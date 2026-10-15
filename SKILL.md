---
name: nk-git-guardrail-hook
description: "A PreToolUse hook for Claude Code that stops before seven risky git and shell commands — force push, git add -A in a shared checkout, making a repo public, pushing while behind the remote, a push that records a mass deletion, a recursive rm on the home folder or the filesystem root, a download run straight in a shell. All seven are on with no config file. The prompt says what is at stake: for the first five, the real incident behind the rule; for the last two, why the step is irreversible or dangerous. Use when several agent sessions share a machine, when an agent pushes on your behalf, or when you keep clicking through the same confirmation (then replay real command history to narrow or harden the rule). Ask by default, deny only where the agent can fix its own command, fail-open if the hook itself breaks."
license: MIT
metadata:
  provenance: own practice (2026-08 to 2026-09); no external source
  version: 0.1.9
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
   `protected_roots` adds your own project folders to rule 6 (paths up to two levels under those roots). The rule's
   built-in targets (the home folder, the filesystem root, the current folder) need no config.
3. Restart the session (hooks load at start). Check it is live: `python3 ${CLAUDE_SKILL_DIR}/scripts/guardrail.py --try "git push --force"` prints `ask` and the reason.
4. Run the quick self-test: `python3 ${CLAUDE_SKILL_DIR}/scripts/guardrail.py --selftest` (original 110 samples plus eight push-line checks; elapsed time printed). The original summary ends `7 of 7 rules on with no config file`. `--selftest-full` additionally runs all push, projection and review regressions, including the hanging-child case; allow several minutes.

The longer regression suites also run directly with `--selftest`:
- `python3 ${CLAUDE_SKILL_DIR}/scripts/push_line_selftest.py --selftest`
- `python3 ${CLAUDE_SKILL_DIR}/scripts/push_review_selftest.py --selftest`
- `python3 ${CLAUDE_SKILL_DIR}/scripts/push_selftest.py --selftest`
- `python3 ${CLAUDE_SKILL_DIR}/scripts/push_work_selftest.py --selftest`
These use throwaway local repositories and take several minutes.

## The rules

| # | Command shape | Decision | Why it exists |
|---|---|---|---|
| 1 | `git push --force` / `-f` / a `+` refspec such as `+main` or `+HEAD:main` (not `--force-with-lease`, with or without `--force-if-includes`) | ask | incident: a shared branch's history rewritten while another session was rebasing onto it |
| 2 | `git add -A` / `.` / `--all` / `*` / `./` / `:/` | deny (configurable) | incident: with several sessions in one checkout, another session's half-written files were swept into a commit |
| 3 | `gh repo create/edit --public`, `--visibility public` or `--visibility=public`, `gh api … private=false` or `visibility=public` | ask | incident: an internal page went public because nobody was asked; publishing publishes all history |
| 4 | `git push` whose actual source is behind its destination on the selected remote (a real `fetch` is run) | ask | incident: a stale local copy was built and deployed over work that only existed on the remote |
| 5 | `git push` whose actual source's pending changes delete ≥ 20 files and 3× more than they add or modify (cumulative from the merge-base with its destination) | ask | incident: an interrupted sparse clone left an empty worktree; the commit recorded 1,000+ deletions; add/commit/push all exited 0 |
| 6 | a recursive `rm` (`-r`, `-rf`, `-fR`, `--recursive`) on the home folder (`~`, `$HOME`, `"${HOME:?}"`, `~/*`, or `*` after `cd ~`), the filesystem root, a folder above home, or `.` / `..`; with `protected_roots` in the config, also on a path ≤ 2 levels under one of those roots | ask | no recorded incident here: the step is irreversible; scratch dirs and temp clones are deliberately not protected |
| 7 | `curl`/`wget` piped into `sh`/`bash`/`python3`/`node`…, or run through a shell argument: `sh -c "$(curl …)"`, `bash <(curl …)`, `eval "$(curl …)"` | ask | no recorded incident: it runs downloaded code nobody has read, the closing step of an "install script" attack chain; save it, read it, report it |

Rules 4 and 5 resolve the repository the command acts on (`git -C <path>` > preceding `cd` commands > cwd), because the
incident behind rule 5 happened in a temporary clone, exactly where a cwd-based check is blind. They resolve each
source/destination pair: no arguments or a remote alone use `remote.<name>.push` or Git's `push.default`
(`simple`, `current`, `upstream`/`tracking`, `matching`), upstream, `branch.<name>.pushRemote`, `remote.pushDefault`,
and `push.autoSetupRemote`. Explicit branches, `HEAD`/`@`, `src:dst`, multiple refspecs, `-u`, `--all`, named remotes
other than origin, and leading `+` are supported. Rule 1 still asks first for a leading `+` or force push.

For a new destination, rule 4 has nothing to count. On a nonempty remote, rule 5 compares with the remote's default
branch; an asking prompt names that branch. An empty remote has no deletion baseline and needs no ask. A missing
or dangling default branch asks only when a new destination needs it; existing destinations are still checked.
For unrelated histories rule 5 compares the destination tree with the source tree. Config and thresholds are unchanged.

**The hook never approves.** It prints only `ask` or `deny` JSON; otherwise it prints nothing and leaves Claude
Code's own permission flow alone. `--try` calls this silent result "allow", but no permission decision was emitted.
Tags (`tag <name>`, tag names/refspecs, `--tags`) and deletions (`:branch`, `--delete`/`-d`) are outside these two
branch-content rules and are silent when no other rule asks. Mixed pushes still check their branch updates.
Normal clean pushes, including new branches, are also silent; no explanatory note is carried by an approval.

Live checks use `git ls-remote --symref` for heads, the default branch and tag names. They fetch only a compared
destination branch (or the default branch needed for a new destination), using the remote's existing fetch mapping.
This can create or update that branch's configured tracking ref, FETCH_HEAD and object database, as an ordinary narrow fetch
does. It does not prune, create `refs/guardrail/*`, import remote tags or widen a single-branch clone's tracking refs.
`--try` has these same fetch effects. No push runs. Details are in [the reference](references/settings.md#push-resolution-and-limits).

Common wrappers (`time`, `command`, `nohup`, `nice`, `exec`, `!`, conditional/loop bodies, `timeout`, `caffeinate`),
quoted assignments, `pushd`, redirections, pipes and comments no longer hide pushes. Literal `xargs git push` and
visible Git pushes behind unresolved wrappers or repository/configuration environment overrides ask. A visible wrapped Git mutation,
such as `xargs git rm`, before commit/push also asks when its resulting tree cannot be resolved. Other xargs
programs are not simulated; `xargs rm` is read as a deleting command below.
Backslash line breaks are joined. Literal quoted scripts sent through a shell here-string or `printf`/`echo` pipe
are read for these branch rules; `cat` here-strings remain data. A visible push in `trap` or an earlier `export GIT_*` asks as unresolved.
When a written push is hidden behind `eval`, a variable, command substitution or text piped into a shell, the hook asks and says "not judged".
The exact `$(git branch --show-current)` and `$(git rev-parse --abbrev-ref HEAD)` substitutions resolve to the branch.
Plain Git aliases that expand to push are read for the branch rules; shell aliases and arbitrary scripts/wrappers
are not interpreted. A visible push in an unresolved shell Git alias asks. Other five rules retain their original
command-text detection, including the force rule's priority on literal `git push` commands.

This hook is for a well-meaning coding agent making readable mistakes; it cannot stop someone writing a command to get past it.
The branch rules treat ordinary commit messages, message variables, dates, file input and quoted heredoc bodies as text, then judge the proposed push.
A recognised deleting or repository-changing command written visibly inside an active substitution, here-string expansion or unquoted heredoc expansion asks as not judged.
Arbitrary scripts and apparently harmless helpers can still hide actions or change arguments and pass silently; the hook does not run helpers or simulate shell splitting to discover what they do.

Message forms include `-m "$(cat <<'EOF' … EOF)"`, `-m` with variables or `$(date …)`, `-F <file>`,
`-F -` with a quoted heredoc or here-string, and a variable used only in a message. Log/echo expansions are
also text. Quoted heredoc delimiters include escaped words. Unquoted bodies retain a cheap textual check
of their active substitutions; quoted bodies remain inert even when they quote a risky command.
The same check reads substitutions in arguments, assignments and redirection operands before those operands
are dropped. It does not prove arbitrary helpers harmless or simulate expansion output, splitting or shell
state. Literal scripts fed directly to a shell remain readable commands; nested literal input is bounded
to 32 levels. Unresolved folders, remote/refspec/source selection and unsupported visible index/history
changes still ask, since they prevent judging what is sent or where.
A later push asks if an earlier branch update could change its destination baseline, including the default
branch used for a new destination. Already up-to-date pushes and unaffected comparison destinations do not
add this ask.

Earlier literal scalar assignments (including `export`, HOME, `~` and another resolved scalar) resolve folder
arguments without running shell code. Quotes are respected, including nested message quotes and quoted heredocs
inside substitutions. Literal `for NAME in ...` lists are checked value by value (at most 64 values and eight nested
loops, within the shared time budget). Positions set with `set --`/`shift`, Bash indexed arrays set on the line,
quoted argument vectors, simple known defaults/alternatives and prefix/suffix trims resolve too. Arrays use Bash's
zero-based indices. Unknown inputs, conditional writes, unsupported operators, command-derived selector values and
unquoted values needing splitting or globbing ask when used by the push. Subshell bindings stay local. An unrelated
helper, `source`, `eval` or `read` does not erase a known selector; a named `read` target becomes unknown.
The scalar reader does not execute a command word held in a variable; a written push following it asks as not judged. Resolved force-push
arguments still ask, and resolved add-all arguments retain the configured add-all decision.
Unrelated environment values, author/committer name/email/date and Git's prompt, logging, editor/pager and
SSH/askpass controls do not add an ask. Simple `env NAME=value git …` is read too. Assignments changing HOME,
XDG_CONFIG_HOME or other Git environment settings still ask because they can select configuration, refs or an index.
Named `printf -v` scalar writes with one literal `%s` argument, and plain `printf %n NAME`, update the resolved
value. Other named formats leave that scalar unknown: a later folder/refspec using it asks, while message-only
use stays quiet. The formatter is not executed or simulated generally.
Whole-word `$(pwd)`, `$(pwd -P)` and `$(git rev-parse --show-toplevel)` directory getters also resolve without
running shell code. An unresolved selector on an earlier commit/history change asks even if its guessed path
looks unrelated to the pushed repository; staging alone does not change the committed source.

Git `-c key=value` accepts identity, colour/advice, credentials, HTTP/GPG/protocol settings, hooks/SSH/askpass/editor/pager,
path quoting, push/commit/tag signing and encoding settings, and core.autocrlf/core.eol; `--no-optional-locks` is also accepted. Accepted options are passed to
the guard's Git reads. Overrides of refs, remote/default selection, worktree/index behavior or other content conversion
are not accepted. Configured names, the selected default remote, matching configured fetch or send addresses
and existing local repository paths (including `.` and file URLs) are judged. Git URL rewrites and `pushurl` are
resolved; each send endpoint is compared separately. Direct addresses use Git's direct-address defaults, not
the named remote's push refspec configuration. Unmatched network addresses and unreadable endpoints ask.
The guard does not discover credentials or contact an unmatched address. A resolved local send address that
would take another fetch-side rewrite is read through an equivalent local path with a command-scoped identity
rewrite. A network endpoint with that second rewrite asks: a filesystem path alias is not assumed valid on a server.

Wildcards, `--mirror` (including config), the `:` matching refspec, tag sources aimed at branches,
non-head/ambiguous destinations, unresolved sources/defaults and unsupported options **ask with a specific
not-judged reason**. Multiple `-C` options resolve in order. Malformed quoting and unresolved directories also ask.
A known non-repository folder is silent because Git fails there; visible repository creation earlier on the line
asks about that future source. `--dry-run`/`-n` skips these two rules.

Push checks share an **8-second budget per command line**, including alias/remote lookup, destination fetches and
comparisons; timeout produces one plain not-judged line. Push reasons are capped at 1,200 characters and new-branch
notes collapse to a count. Normal non-push built-ins start no extra Git subprocesses. Startup and the five other
rules' command-text checks are outside this budget.

Supported commit-and-push lines are projected without executing the earlier commands: plain `commit` uses the index;
`commit -a` uses tracked working files as they are before the line runs; earlier `add -u`, literal paths, `add -A`/`.` update that proposed index,
including nonignored new files. The existing add-all rule still asks/denies first unless configured off. Simple
file `git mv`/`git rm` and staged restore are projected too; `git stage` is read as `git add` by these branch rules.
The history check uses the proposed commit's parent; deletions use its proposed tree, including from subfolders.
The command directory and repository root resolve symbolic links. An absolute staging path written through
an alias of the repository directory is still compared as written and asks as outside the working tree.
Clean commits stay silent; wipes already removed or staged before the line runs, or projected through supported
`git rm`/`git mv`, ask with the count. Literal `rm`/`rmdir`/`unlink` (including absolute command paths),
`find -delete`/direct `-exec` or `-execdir rm`/`rmdir`/`unlink`, `xargs rm` and `git clean` are read before
worktree-consuming staging/commit and push. This includes `sudo`, `command`, `env`, `time`, `nohup`, `nice`, `exec`,
`!`, `timeout` and `caffeinate`, plus if/for bodies, subshells and brace groups. They ask as not judged for an
unresolved removal of candidate paths; `xargs rm` and non-dry-run `git clean` ask without checking paths.
Find predicates are not evaluated, so a find cleanup can ask even if it removes no tracked files.
Literal, resolved `rm` targets confined to untracked build folders before `commit -a` stay quiet. Files removed earlier on the same line by a
script, another program or unmodelled Git plumbing are not seen; such a line can stay silent despite a wipe.
Deletion matching does not expand `{sub,build}` or match alternate case spellings on case-insensitive disks.
Custom wrappers hiding the command word, `env -S`/`-C`, and `find -exec sh -c` removal are not simulated and can
also leave a wipe silent. Plain listing commands, including `git branch -vv`, do not change the proposed push.

Simple branch checkout/switch and branch creation resolve the future source. Deleting another branch, `config user.*`
and simple tag creation do not trigger a blanket ask. Successful `&&`-connected pull/merge is projected when it
is already up to date or can only fast-forward: source ancestry is taken from the resulting commit, so a different
pushed source still gets its own behind/deletion comparison. A clean fast-forward with no removals can precede
another projected commit; dirty future index/worktree state, divergent/rewritten history, a different rebase fork
point and unsupported history options ask. Autostash configuration alone does not add an ask. Ordinary tracking
fetches, including prune/tag options, do not rewrite a plain pushed source. Fetches writing local branch refs or
shallow history ask; custom/partial mappings before a merge and a changed FETCH_HEAD target also ask. Pull and
tracking-branch merge require a readable target and mapping. The earlier commands are never executed. Known
soft/mixed/hard reset targets, single-parent amend, `--only` and `--include` path commits are projected. Rebase,
cherry-pick/am/revert, push configuration changes, unsupported staging options/pathspecs, content-converting
filters/encodings or working-tree submodules ask why their future state cannot be projected. Ordinary text/EOL
normalization is projected; assume-unchanged/skip-worktree files retain their index content as Git does. Plain
commits omit intent-to-add entries. Message/signing/cleanup/trailer options do not change the proposed tree.
A projected commit needs an existing branch parent; a commit after switching to a different existing tree also
asks. No index, worktree, HEAD or commit object is written by projection. Arbitrary scripts,
hidden mutations inside shell aliases, dynamically assembled shell input and earlier tool calls remain outside this reader.
See [the push reference](references/settings.md#push-resolution-and-limits) for the policy and replay details.

The four regression scripts ship with the skill: `push_line_selftest.py` is required by `--selftest` and supplies
the quick checks and full projection cases (full runs reach fixtures through a symbolic link);
`push_selftest.py`, `push_review_selftest.py` and `push_work_selftest.py` supply the opt-in resolution, safety and
ordinary-line/risky-twin suites. The latter can write an invented comparison with `--output <folder>`; an old
job snapshot is optional and is not an installation dependency.
Saved old hooks and comparison logs are job evidence outside the skill, not installation files.

## A first look: your own last 30 days

`python3 ${CLAUDE_SKILL_DIR}/scripts/replay.py --summary` reads the Claude Code session files under `~/.claude/projects`
(subagent sessions included), takes every shell command of the last 30 days (`--days N` for another period) and puts
each one that a rule could read through the hook. It prints seven lines, one per rule: how many of those commands the
hook would have refused or asked about, one of them as an example, and a plain `0` where the rule never fired. It works
before the hook is installed, so it is the quickest way to see whether these seven rules are about your work.

- Each command is judged in its recorded folder. Missing recorded or resolved folders are counted separately as
  "could not be replayed", without substituting the summary's current folder or counting an intervention.
- Nothing is pushed, committed or changed in a working tree, and no network is reached. The two push lines (behind its
  remote, deletes most of a repository) are judged on what is already on disk: each repository as it is today, against
  its remote as of your last fetch. The screen says "as of your last fetch" on both lines; a repository you have not
  fetched lately can be further behind than it says. An uncached local send endpoint can be read directly from
  its on-disk refs; an uncached network send endpoint asks instead of borrowing a different fetch view.
- `--summary --fetch` reads each selected remote's names once and fetches each compared destination once per
  repository, using the live resolver. Failed queries are remembered too; multiple destinations can require multiple fetches.
- Results are cached per source and destination, not just repository. Not-judged asks have one summary line and
  are counted once, with fixed reason categories printed beneath the total. Silent tag/deletion results emit no notice and are not counted as asks.
- Offline summaries use ordinary remote-tracking refs and their symbolic default branch, without network access.
  Matching configured addresses use the named remote's cached refs; local path destinations can be read on disk.
  A new destination with no cached default, missing comparison objects, or an uncertain short tag destination asks as not judged.
- The examples are your own commands and can hold private paths. `--no-examples` prints the counts alone.
- `--summary --reason-sentences` adds counts per fixed hook sentence and suppresses examples. Labels come from
  a closed catalogue with no command, folder, remote or branch interpolation; unknown templates use a fixed
  generic sentence. Unavailable folders remain separate from these counts.
- `python3 ${CLAUDE_SKILL_DIR}/scripts/replay.py --demo` prints the same screen from an invented history (a made-up
  month of commands and a temporary repository that is three commits behind a remote next to it) and reads nothing of yours.

## Design rules (why it is built this way)

- **Ask, not deny** — except where the fix belongs to the agent. `git add -A` is denied with the fix in the
  reason (`git add -- <paths>`) because a human clicking "allow" 169 times in a week is a cost moved to the
  wrong person; the agent can correct its own command.
- **Fail-open.** Any internal error → exit 0, no output. A guardrail that blocks every command is worse
  than none. (Detectors are the opposite: they must fail loud. Know which one you are writing.)
- **Five rules cite an incident; two say why they exist.** Rules were meant to come only from incidents,
  because imagined risks produce false positives, and a few false positives teach people to click through
  everything. A recursive `rm` on the home folder and `curl | sh` are the exceptions: neither has a recorded incident
  here, and their prompts say what is at stake instead — the `rm` cannot be undone; `curl | sh` runs code nobody has read.
- **Heredoc bodies are data**, unless a shell consumes them (`bash <<EOF`, `… | sh`, `eval`, `ssh host <<EOF`).
  Quoted strings are ignored, but `$(…)` inside quotes is kept — it runs — and so is a quoted string handed to
  a shell (`bash -c '…'`, `sh -lc "…"`, `eval '…'`). A quoted single word keeps its text for rules 3 and 6, so
  `"$HOME"` and `--visibility "public"` are read as what they name.
- **Same-segment only.** A rule looks at its own command segment (up to `;`, `&&`, `|`, newline); a path in
  the next command is not blamed on this `rm`. The price: a target passed through a variable is invisible.

## Tuning with real history

When the same prompt keeps appearing: `python3 ${CLAUDE_SKILL_DIR}/scripts/replay.py --days 7` feeds every
Bash command your sessions ran (subagents included) through the hook and prints the decision distribution
with samples per reason (for each past push the hook runs its `git fetch`, as before a live one).
Run it before and after a rule change; the diff is the evidence. Two outcomes:
false positives → narrow the rule; true positives that the agent can fix itself → deny with the fix in the
reason. The only prompts worth keeping are the ones a human should actually decide.

## Boundaries (what it cannot see)

- Seven rules, not a full safety net. `git reset --hard`, `git clean -f`, `git checkout -- .` and `git branch -D`
  are allowed: none has an incident behind it here. [cc-safety-net](https://github.com/kenryu42/claude-code-safety-net)
  blocks those and many more, for more agents; the two can run side by side.
- Rule 6 asks about four targets with no config: the home folder, the filesystem root, a folder above home, and `.` or
  `..`. It does not ask about a folder inside home (`~/Documents`), a bare `*` in an ordinary folder, or a project
  folder, unless `protected_roots` names it. cc-safety-net asks about every recursive `rm` outside the working directory.
- Only Bash. A malicious file written with an editor tool and run some other way is not seen.
- Targets passed through variables other than `$HOME` and `$PWD` (`R=~/projects/app; rm -rf $R`) and heredoc bodies fed to
  python/node that shell out. Real isolation is a sandbox; this hook removes the most common step.
- It reads the command, not the files the command runs. A download saved first and run second (`curl -o i.sh …; sh i.sh`) is two
  ordinary commands to it, and `python3 -c "$(curl …)"` is not matched (only the shell forms are).
- Deleting by other means is not seen: `find ~ -delete`, `xargs rm`, a `cd` in an earlier command of the session.
- `replay.py --summary` counts what the hook says today. A push that was behind its remote last week and has been pulled
  since counts as 0; a command whose recorded or resolved folder is gone is reported as unable to replay. Without `--fetch`
  it knows each remote only as of your last fetch.
- The full replay (`replay.py` without `--summary`) goes through the hook's real entry point, so it runs the hook's
  fetch for each past branch push it replays.

## Provenance

Own practice, 2026-08 to 2026-09. Started as six rules after a review of the author's own setup found
enforcement to be its thinnest part — many red lines, nothing enforcing them. Rules were then narrowed or hardened using a
seven-day replay of real command history (about 7,500 commands): one rule went from ask to deny after
169 prompts with no true positive; a rule with no incident behind it was removed, and another was cut
down to its `curl | sh` line, kept as rule 7 without an incident. No external source.
