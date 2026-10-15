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

## Push resolution and limits

Version 0.1.9 (fix round 3) reads each visible push's branch sources and destinations. Implicit pushes use
`remote.<name>.push` or `push.default` (`simple`, `current`, `upstream`/`tracking`, `matching`), upstream and
`push.autoSetupRemote`. Remote choice follows an explicit name, branch `pushRemote`, `remote.pushDefault`,
branch `remote`, then the sole remote or origin. Branches, full head refs, `HEAD`/`@`, `src:dst`, multiple refspecs,
`-u`, `--all` and leading `+` are supported. The other five rules retain their command-text detection and priority.

The behind count is `source..destination`; deletion counts are cumulative from the merge-base to the source,
or from the destination tree to the source if there is no merge-base. All behind comparisons precede deletion
comparisons. Asks always name the source, remote and destination, including same-name and `--all` pushes.

A new destination has no behind count. On a nonempty remote its deletion baseline is the advertised default
branch, named in an ask. An empty remote has no baseline and is silent. A missing/dangling default does not
prevent checking existing destinations; a new destination that needs that default asks as not judged.

Live checks and `--try` first run `git ls-remote --symref <remote> HEAD refs/heads/* refs/tags/*`, which reads
names/OIDs without writing refs or downloading tags. Only compared destination branches (or their default
baseline) are fetched: `git fetch -q --no-tags --no-recurse-submodules <remote> refs/heads/<branch>`.
This creates or updates FETCH_HEAD, objects and any matching configured tracking ref, just as a narrow fetch does.
No pruning, broad heads fetch, automatic tag following or `refs/guardrail/*` writes occur. A shallow clone
can gain the destination objects required for a comparison; unrelated tracking branches are not introduced.

Push checks share an 8-second deadline per command line, including alias lookup, remote-name lookup, fetches
and comparisons. Timeout asks with one plain line, without a raw exception or command/path dump. Asking
reasons are capped at 1,200 characters; new-destination notes collapse to a count. Process startup and the
five other command-text rules are outside that budget. Ordinary non-push Git built-ins start no extra Git
subprocesses. Unknown Git subcommands can require a local alias lookup.

| Form | Hook output / coverage |
|---|---|
| Clean branch update, including a checked new branch | nothing; the hook abstains, it never approves |
| `:branch`, `--delete`/`-d`, tags, `tag <name>`, `--tags` | nothing unless another rule asks; these branch-content rules do not guard branch removal or tag publication |
| Mixed branches/tags/deletions; `--follow-tags` | branch updates checked; tags/deletions omitted from these comparisons |
| Plain Git aliases expanding to push | branch rules resolve the alias; the other five retain their command-text matching |
| `time`, `command`, `nohup`, `nice`, `exec`, `!`, conditional/loop bodies, `timeout`, `caffeinate` | visible Git push read; no wrapper is executed |
| Redirections (`N>`, `N>&M`, `>`, `>>`, `<`, `<<<`), pipes and comments | redirections/targets/comments dropped before refspec parsing |
| `cd`, simple `pushd`/`popd`, subshells, repeated `git -C` | directory resolved in order; unknown directory-stack operations or selector values ask |
| Literal `xargs git push`, visible pushes behind unresolved wrappers/environment assignments, visible wrapped Git mutations before commit/push, visible push in a shell Git alias | ask when the execution context or resulting tree cannot be resolved; other xargs programs are not simulated |
| Plain commit; commit `-a`; supported preceding staging, `git mv`/`git rm` | index/tracked files as they are before the line, plus supported Git operations, compared without writes; clean silent, existing/projected wipe count asks; subfolders supported |
| `git stage` | synonym for `git add` in the branch projection |
| Literal deleting commands before worktree-consuming staging/commit and push | `rm`/`rmdir`/`unlink` (also absolute paths), `find -delete`/direct `-exec`/`-execdir rm`/`rmdir`/`unlink`, `xargs rm`, `git clean`: read through the listed wrappers/bodies below; not-judged ask for unresolved candidate removal; resolved `rm` of untracked build targets before `commit -a` stays quiet |
| Plain read-only commands: status/log/diff/show, branch listing (including `-vv`), remote `-v` | no mutation ask |
| Simple checkout/switch or new branch; `config user.*`; deletion of another branch; simple new tag | source/tag resolved; no blanket mutation ask |
| Successful `&&` pull/merge, no-op or fast-forward, ordinary tracking mapping | resulting source ancestry/tree judged; a clean fast-forward without removals can precede a commit; divergent/rewritten history, dirty future state or unsupported options ask |
| Known soft/mixed/hard reset, single-parent amend, `--only`/`--include` commits | future parent/tree/index projected without writes |
| Earlier rebase/cherry-pick/am/revert, push config mutation, unsupported commit/staging effects | specific not-judged ask: future history/tree cannot be projected |
| Backslash line breaks; exact current-branch substitutions | joined/resolved before refspec parsing |
| Literal quoted shell input through here-string or printf/echo pipe | branch push text read; cat input remains data |
| Visible trap push, earlier `export GIT_*` | not-judged ask for unresolved execution context |
| `$NAME push`, command-word substitution output followed by `push`, a written push in `eval` or unreadable text piped into a shell | ask as not judged; the generated command is not executed |
| Arbitrary scripts/helpers with no written push hint | outside the branch rules' scope; may pass silently |
| Wildcards, mirror/configured mirror, `:` matching refspec | ask: broad updates unresolved; configured `push.default=matching` is supported |
| Configured/default remote, matching fetch/send address, existing local repository path/`.`/file URL | actual send endpoint judged; direct addresses use direct-address defaults; unmatched network addresses are not contacted and ask |
| Explicit `pushurl`, multiple named URLs, Git URL rewrites | each resolved send endpoint judged separately; unavailable names/objects ask |
| Resolved send address also matches another fetch-side rewrite | local endpoint read through an equivalent path with a command-scoped identity rewrite; network endpoint asks rather than reading the wrong repository |
| Literal scalar assignments, HOME/`~`, literal for lists, line-set positions/Bash indexed arrays, known defaults and trims | each resolved value checked; unknown/conditional writes, unsupported operators, command-derived selectors and unquoted splitting/globbing ask |
| Identity/colour/advice/credentials/HTTP/GPG/protocol, hooks/SSH/askpass/editor/pager, path quoting, signing/encoding, core.autocrlf/core.eol `-c` settings; `--no-optional-locks` | accepted and forwarded to Git reads; refs, remote/default, index/worktree or other conversion overrides still ask |
| Unsupported push/global Git options, SHA/expressions/unresolved sources, non-head/ambiguous destinations, tag source aimed at a branch, invalid defaults, malformed quoting/expansions | ask with the specific reason that form was not judged |
| Known non-repository push folder | nothing; Git fails there, and the hook does not approve it; visible earlier repository creation asks about the unknown future source |
| `--dry-run`/`-n` | branch rules skipped; command-text rules still run |

All JSON permission decisions are `ask` or `deny`. Silence leaves Claude Code's own permission flow intact;
there is no allow JSON or approval carrying an informational notice. `--try` uses its historic word `allow`
for silence. Unexpected internal errors still fail open. Only the first asking/denying rule prints a decision.

The parser is not a shell interpreter. `plan_line` projects supported commits from the index, or tracked working
files as they are before the line runs for `-a`. Earlier `add -u`, literal paths, `add -A`/`.` update the virtual index,
with ignored new files omitted; `stage` is read as `add`. Simple file `git mv`/`git rm` and staged restore are supported;
the add-all command-text rule keeps its original priority. Wipes already removed/staged before the line, or projected
through these supported Git operations, ask with counts. The listed literal deleting commands are read through
`sudo`, `command`, `env`, `time`, `nohup`, `nice`, `exec`, `!`, `timeout`, `caffeinate`, if/for bodies, subshells and
brace groups. Before staging affected worktree paths or `commit -a`, and a push, unresolved removal asks as not
judged; it is not executed or counted. `xargs rm` and non-dry-run `git clean` ask without path checks; find predicates
are not evaluated, so harmless find cleanup can also ask. `xargs git rm` stays in the Git reader and asks even before
a plain index commit. Other xargs commands are not treated as removals merely because an argument says `rm`.
Resolved `rm` of only untracked build folders before `commit -a` is quiet. A script, another program or unmodelled Git plumbing
that removes files earlier on the line is not seen, so even a wipe can remain silent. Deletion matching does not
expand brace targets (`{sub,build}`), match alternate case spellings on case-insensitive disks, simulate custom
wrappers hiding the command word, `env -S`/`-C`, or `find -exec sh -c` removal; these can also leave a wipe silent.
The command directory and repository root resolve symbolic links. An absolute staging path written through
an alias of the repository directory is still compared as written and asks as outside the working tree.
Behind counts use the parent commit; deletion counts compare the merge-base with the projected tree. No object,
HEAD, index or worktree is written. Known single-parent amend and path-limited commits are projected. Message,
signing, cleanup and trailer options do not affect the proposed tree. Ordinary text/EOL normalization is projected;
assume-unchanged/skip-worktree files keep their index content. Unsupported pathspecs/commit options,
custom filters/encodings or working-tree submodules,
a commit without an existing branch parent or after changing to a different existing tree, and unknown future
history ask specifically. Plain commits omit intent-to-add entries. Harmless config changes and deletion of another
branch do not affect the push. Tracking-only fetch options do not add an ask before a plain push; local branch or
shallow-history writes, a changed FETCH_HEAD merge target, and custom/partial tracking mappings before a merge
retain an ask about the future ancestry.
Simple tag creation is resolved even if the tag is not yet on disk. Arbitrary scripts, dynamically assembled
shell input, hidden shell-alias mutations and other command-word expansions may remain invisible; literal visible
pushes in the documented unresolved forms ask. Quoted script feeding applies to the branch rules only.
HOME/XDG_CONFIG_HOME and Git environment overrides that can change configuration/refs/index still ask.
Unrelated environment values, author/committer identity/date, prompt, logging, editor/pager and SSH/askpass
controls do not add an ask; simple `env NAME=value git …` is read. Other env wrapper options remain unresolved. Resolved
force-push and add-all arguments retain their asking/configured decisions rather than escaping the text detectors.
Named `printf -v` scalar writes with one `%s` argument, and plain `printf %n NAME`, resolve without execution.
Other named formats leave the value unknown; a subsequent folder/refspec using it asks, but message-only use
does not. Changes to configuration/index-selecting environment names still ask.
Whole-word `$(pwd)`, `$(pwd -P)` and `$(git rev-parse --show-toplevel)` getters resolve from the known command
directory. Unresolved selectors on earlier commits/history changes cannot be discarded as unrelated;
index/worktree staging without a commit still leaves the pushed committed source unchanged.

These branch rules target readable mistakes by well-meaning agents, not deliberate bypasses. Ordinary
message variables/date substitutions, `-m "$(cat <<'EOF' … EOF)"`, file messages, quoted message heredocs
and log/echo output are treated as text. Quoted delimiters include escaped words. An active substitution
whose own written text contains a recognised deleting or repository-changing command asks as not judged;
the check also reads unquoted heredoc expansions, here-strings, assignments and redirection operands.
It does not execute helpers or prove them harmless. A written push behind a constructed command word or
`eval` asks as not judged; scripts and helpers without a written push hint can still conceal actions and pass silently.
Literal scripts supplied directly to a shell remain readable;
nesting is bounded to 32 levels. Folder, remote/refspec/source uncertainty and unsupported visible
history/index changes still ask because the proposed update cannot be determined. A later push also asks
when an earlier branch update could change the same destination baseline (including a default branch used
for a new destination); pushes already up to date or comparing unaffected destinations do not add this ask.

`--selftest` runs the original 110 samples and eight quick push-line regressions (about 11 seconds here); it prints
elapsed time. `--selftest-full` also runs all projection, 83 push-resolution and 100 review cases, including the
eight-second hanging-child test; allow several minutes. Full projection fixtures are reached through a symbolic
link. The four standalone test scripts ship; `push_line_selftest.py` is required even for the default self-test.
`push_work_selftest.py` adds ordinary lines, measured wipe twins, history boundaries and replay accounting;
an old job snapshot is optional, used only for comparison and change-off checks.

`replay.py --summary` calls these same branch functions. Without `--fetch`, remote lookup reads only ordinary
tracking refs and a symbolic remote HEAD, or an uncached local endpoint's on-disk refs; fetch is suppressed and an
accidental `ls-remote` is rejected. A separate network send endpoint without matching cached refs asks rather
than borrowing a fetch endpoint's view.
Local tag names do not prove a remote tag exists: an uncertain short destination asks. No legacy private
default/tag snapshots are required. Results describe cached state today, not historical state at execution.
With `--fetch`, names are read once per repository/remote, each compared destination is fetched once, and
failed lookups are memoized too; accepted Git options are part of the cache key. Multiple destinations can mean
multiple narrow fetches. Matching configured addresses use cached tracking refs offline; local destinations can
be read on disk, but absent source-side comparison objects still ask. Not-judged asks have one summary line and
are counted once, broken down into fixed reason categories. Missing recorded or resolved repository folders
are counted as "could not be replayed", apart from interventions and not-judged asks. No fallback folder is guessed.
Silent deletions/tags produce no notice or ask count.
`--summary --reason-sentences` additionally prints counts per fixed hook sentence and suppresses examples.
The sentence labels come from a closed catalogue: no command, directory, remote or branch interpolation is
printed, and unknown templates use a fixed generic sentence. Unavailable folders remain a separate count.
Full replay uses the actual hook entry point and can contact the configured remote. Config is unchanged.
