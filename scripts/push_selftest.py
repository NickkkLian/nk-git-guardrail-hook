#!/usr/bin/env python3
"""Push regressions for the current hook API: local bare remotes only."""
import contextlib, importlib.util, io, json, os, pathlib, subprocess, sys, tempfile


def run(hook=None):
    hook = os.path.abspath(hook or os.path.join(os.path.dirname(__file__), 'guardrail.py'))
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('push_test_hook', hook)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    env = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.com',
               GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.com',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    rows, failed = [], 0
    with tempfile.TemporaryDirectory(prefix='push_rules_') as tmp:
        env['GUARDRAIL_CONFIG'] = os.path.join(tmp, 'no-config')
        def g(repo, *args):
            r = subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, env=env)
            if r.returncode:
                raise RuntimeError(f"git {args}: {r.stderr}")
            return r.stdout.strip()
        bare, work, peer = [os.path.join(tmp, n) for n in ('remote.git', 'work', 'peer')]
        g(tmp, 'init', '-q', '--bare', bare); g(bare, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        g(tmp, 'clone', '-q', bare, work); g(work, 'checkout', '-q', '-b', 'main')
        for i in range(40): pathlib.Path(work, f'f{i}').write_text(str(i))
        g(work, 'add', '.'); g(work, 'commit', '-qm', '40 files'); g(work, 'push', '-qu', 'origin', 'main')
        g(work, 'checkout', '-qb', 'wip'); g(work, 'push', '-q', 'origin', 'wip')
        g(work, 'rm', '-qr', '.'); g(work, 'commit', '-qm', 'wipe'); g(work, 'branch', 'unpublished')
        g(work, 'checkout', '-q', 'main'); g(work, 'tag', 'v1')
        g(tmp, 'clone', '-q', bare, peer)
        pathlib.Path(peer, 'new').write_text('new'); g(peer, 'add', '.'); g(peer, 'commit', '-qm', 'remote only')
        g(peer, 'push', '-q', 'origin', 'main:later'); g(work, 'fetch', '-q', 'origin')
        g(work, 'remote', 'add', 'backup', bare); g(work, 'fetch', '-q', 'backup')
        g(work, 'symbolic-ref', 'refs/remotes/backup/HEAD', 'refs/remotes/backup/main')
        rewrite = f'url.{os.path.join(tmp, "other.git")}.pushInsteadOf'
        keys = ['remote.origin.push', 'remote.backup.push', 'remote.pushDefault', 'branch.main.pushRemote',
                'branch.wip.pushRemote', 'branch.main.remote', 'branch.main.merge', 'branch.wip.remote',
                'branch.wip.merge', 'branch.unpublished.remote', 'branch.unpublished.merge',
                'push.default', 'push.autoSetupRemote', 'remote.origin.mirror', 'remote.origin.pushurl', 'push.followTags',
                'remote.origin.url', rewrite]
        def reset(branch='main', cfg=()):
            g(work, 'checkout', '-q', branch)
            for key in keys:
                subprocess.run(['git', '-C', work, 'config', '--unset-all', key], capture_output=True, env=env)
            for key, value in [('remote.origin.url', bare), ('push.default', 'simple'), ('branch.main.remote', 'origin'),
                               ('branch.main.merge', 'refs/heads/main'), ('branch.wip.remote', 'origin'),
                               ('branch.wip.merge', 'refs/heads/wip'), *cfg]: g(work, 'config', '--replace-all', key, value)
        def judge(command, hidden=False):
            r = subprocess.run([sys.executable, hook], input=json.dumps({'tool_name':'Bash',
                'tool_input':{'command':command}, 'cwd':work}), capture_output=True, text=True, env=env)
            if r.returncode or r.stderr: raise RuntimeError(f'hook crashed: {r.returncode}: {r.stderr}')
            out = json.loads(r.stdout)['hookSpecificOutput'] if r.stdout.strip() else {}
            result = (out.get('permissionDecision', 'allow'), out.get('permissionDecisionReason', ''))
            # Direct check must agree and must not crash: fail-open cannot produce a passing allow.
            saved = dict(os.environ)
            os.environ.update(env)
            evaluated = []
            real_evaluate = mod.evaluate_push
            def observe(repo, words, cfg=None):
                evaluated.append((repo, words))
                return real_evaluate(repo,words,cfg)
            mod.evaluate_push = observe
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    try: mod.check(command, work, mod.load_config())
                    except SystemExit: pass
                direct = json.loads(buf.getvalue())['hookSpecificOutput'] if buf.getvalue().strip() else {}
                assert result == (direct.get('permissionDecision','allow'), direct.get('permissionDecisionReason',''))
                assert out.get('permissionDecision') != 'allow', 'hook must never approve'
                if result[0] == 'allow' and not hidden:
                    assert r.stdout == '' and evaluated, 'a silent allow must still have read the push'
                    repo, words = evaluated[-1]
                    with mod.push_budget():
                        remote, pairs, _ = mod.resolve_push(repo,words)
                    if words == ['origin','main']: assert pairs == [('refs/heads/main','refs/heads/main')]
                    if words == ['origin','clean:main']: assert pairs == [('refs/heads/clean','refs/heads/main')]
            finally:
                mod.evaluate_push = real_evaluate
                os.environ.clear(); os.environ.update(saved)
            return result
        def case(label, cmd, want='ask', text='this push deletes 40 files', branch='main', cfg=(), setup=None):
            nonlocal failed
            reset(branch, cfg)
            if setup: setup()
            got, why = judge(cmd, hidden=label.startswith('hidden: '))
            ok = got == want and text in why; failed += not ok
            rows.append(dict(label=label, command=cmd, decision=got, reason=why, passed=ok))
            print(f"  {'✔' if ok else '✘'} {label}: {cmd} => {got}" + (f" (want {want}, reason containing {text!r})" if not ok else ''))
        case('reviewer: off-checkout wipe', 'git push origin wip:main')
        case('branch name off checkout', 'git push origin wip')
        case('full branch refs', 'git push origin refs/heads/wip:refs/heads/main')
        case('unpublished source', 'git push origin unpublished:main', branch='unpublished')
        case('clean source, wiped checkout', 'git push origin main', 'allow', '', branch='wip')
        case('HEAD to different name', 'git push origin HEAD:main', branch='unpublished')
        case('HEAD implied destination', 'git push origin HEAD', branch='unpublished')
        case('several refspecs', 'git push origin main wip:target')
        case('-u', 'git push -u origin unpublished:main', branch='unpublished')
        case('--all', 'git push --all origin')
        case('non-origin remote', 'git push backup wip:main')
        case('quoted words', 'git push "origin" "wip:main"')
        case('no args: configured refspec', 'git push', cfg=[('remote.origin.push','wip:main')])
        case('remote alone: configured refspec', 'git push origin', cfg=[('remote.origin.push','wip:main')])
        case('no args: upstream', 'git push', branch='unpublished', cfg=[('push.default','upstream'),
             ('branch.unpublished.remote','origin'), ('branch.unpublished.merge','refs/heads/main')])
        case('no args: current', 'git push', branch='unpublished', cfg=[('push.default','current')])
        case('remote alone: simple', 'git push origin', branch='unpublished', cfg=[('push.autoSetupRemote','true')])
        case('no args: matching', 'git push', cfg=[('push.default','matching')])
        case('pushRemote precedence', 'git push', cfg=[('branch.main.pushRemote','backup'), ('remote.backup.push','wip:main')])
        case('pushDefault precedence', 'git push', cfg=[('remote.pushDefault','backup'), ('remote.backup.push','wip:main')])
        case('behind named source/destination', 'git push origin main:later', text='behind origin')
        case('behind remote alone', 'git push origin', text='behind origin', cfg=[('remote.origin.push','main:later')])
        case('behind upstream', 'git push', text='behind origin', cfg=[('push.default','upstream'), ('branch.main.merge','refs/heads/later')])
        case('behind several refs', 'git push origin main main:later', text='behind origin')
        case('behind other remote', 'git push backup main:later', text='behind backup')
        case('new destination default baseline', 'git push origin wip:newbranch')
        case('new clean destination (silent)', 'git push origin main:newbranch', 'allow', '')
        case('delete colon', 'git push origin :main', 'allow', '', branch='wip')
        case('delete option', 'git push --delete origin main', 'allow', '', branch='wip')
        case('delete short option', 'git push -d origin main', 'allow', '')
        case('tag name', 'git push origin v1', 'allow', '')
        case('tag refspec', 'git push origin refs/tags/v1:refs/tags/v1', 'allow', '')
        case('all tags', 'git push origin --tags', 'allow', '')
        case('mixed tag and wipe', 'git push origin v1 wip:main')
        case('mixed deletion and wipe', 'git push origin :main wip:target')
        case('follow-tags still checks branch', 'git push origin --follow-tags', cfg=[('remote.origin.push','wip:main')])
        case('Git -C', f'git -C "{work}" push origin wip:main')
        linked = os.path.join(tmp, 'work with spaces'); pathlib.Path(linked).symlink_to(work)
        case('quoted cd path', f'cd "{linked}" && git push origin wip:main')
        case('later cd cannot select push repo', 'git push origin wip:main; cd /tmp')
        case('simple triangular current', 'git push backup', branch='unpublished')
        case('detached HEAD explicit branch', 'git push origin HEAD:refs/heads/main',
             setup=lambda: g(work, 'checkout', '-q', '--detach', 'unpublished'))
        case('multiple remote URLs', 'git push origin wip:main', 'ask', 'this push deletes 40 files',
             setup=lambda: g(work, 'config', '--add', 'remote.origin.url', os.path.join(tmp, 'other.git')))
        case('push URL rewriting', 'git push origin wip:main', 'ask', 'could not be read', cfg=[(rewrite, bare)])
        case('later push after dry run', 'git push --dry-run origin main; git push origin wip:main')
        case('shell argument', "bash -c 'git push origin wip:main'")
        # SAFETY.md's eleven hidden pushes must ask without pretending to judge them.
        for label, command in [
            ('eval quoted', "eval 'git push origin wip:main'"),
            ('variable command', 'GIT=git; $GIT push origin wip:main'),
            ('substitution command', '$(which git) push origin wip:main'),
            ('backtick command', '`which git` push origin wip:main'),
            ('eval double quoted', 'eval "git push origin wip:main"'),
            ('text piped to shell', 'echo git push origin wip:main | bash'),
            ('eval bare push', 'eval git push'),
            ('substitution bare push', '$(which git) push'),
            ('backtick bare push', '`which git` push'),
            ('piped bare push', 'echo git push | bash'),
            ('variable bare push', 'GIT=git; $GIT push'),
        ]:
            case('hidden: ' + label, command, 'ask', 'not judged', branch='wip')
        case('allow notice does not bypass rm', 'git push origin :main; rm -rf ~', 'ask', 'recursive rm', branch='wip')
        for label, cmd, text, cfg in [
            ('wildcard', "git push origin 'refs/heads/*:refs/heads/*'", 'wildcard', []),
            ('matching colon', 'git push origin :', 'matching', []),
            ('mirror', 'git push --mirror origin', 'mirror', []),
            ('configured mirror', 'git push origin', 'mirror', [('remote.origin.mirror','true')]),
            ('URL', 'git push https://example.invalid/repo.git wip:main', 'remote name', []),
            ('path', f'git push {bare} wip:main', 'this push deletes 40 files', []),
            ('unknown option', 'git push --mystery origin wip:main', 'option', []),
            ('variable', 'git push "$REMOTE" wip:main', 'shell expansion', []),
            ('source expression', 'git push origin HEAD~1:main', 'source HEAD~1 is not an unambiguous local branch', []),
            ('non-branch destination', 'git push origin wip:refs/notes/test', 'destination refs/notes/test is not a valid branch', []),
            ('separate pushurl', 'git push origin wip:main', 'this push deletes 40 files', [('remote.origin.pushurl',bare)]),
            ('push.default nothing', 'git push', 'push.default', [('push.default','nothing')]),
            ('simple mismatch', 'git push', 'simple', [('branch.main.merge','refs/heads/later')]),
            ('remote read failure', 'git push broken main', 'remote broken could not be read', []),
            ('tag source to branch', 'git push origin v1:main', 'tag source', []),
            ('global config override', 'git -c push.default=current push origin wip:main', 'global option', []),
            ('multiple -C', f'git -C "{work}" -C . push origin wip:main', 'this push deletes 40 files', []),
            ('environment override', 'GIT_DIR=elsewhere git push origin wip:main', 'environment', []),
            ('malformed quoting', 'git push origin "wip:main', 'quoting', []),
            ('cd through variable', 'cd "$SOME_REPO" && git push origin wip:main', 'cd uses', []),
            ('missing upstream', 'git push', 'upstream', []),
            ('SHA source', f'git push origin {g(work, "rev-parse", "wip")}:main', f'source {g(work, "rev-parse", "wip")} is not an unambiguous local branch', []),
            ('other global option', f'git --git-dir="{work}/.git" push origin wip:main', 'global option', []),
            ('local dot remote', 'git push . wip:main', 'this push deletes 40 files', []),
            ('incompatible --all', 'git push --all origin wip:main', 'combined', []),
            ('delete without destination', 'git push --delete origin', 'no destination', []),
        ]:
            if label == 'remote read failure': g(work, 'remote', 'add', 'broken', os.path.join(tmp,'absent.git'))
            case(label, cmd, 'ask', text, cfg=cfg, branch='unpublished' if label == 'missing upstream' else 'main')
        case('implicit detached HEAD', 'git push', 'ask', 'detached',
             setup=lambda: g(work, 'checkout', '-q', '--detach', 'main'))
        case('new detached short destination', 'git push origin HEAD:newshort', 'ask', 'detached',
             setup=lambda: g(work, 'checkout', '-q', '--detach', 'main'))
        reset(); got, why = judge('git push origin +wip:main')
        decision, reason = mod.evaluate_push(work, ['origin', '+wip:main'])
        ok = got == 'ask' and 'force push' in why and decision == 'ask' and 'this push deletes' in reason
        failed += not ok
        rows.append(dict(label='leading + resolver', command='git push origin +wip:main', decision=got, reason=why, passed=ok))
        print(f"  {'✔' if ok else '✘'} leading +: force rule {got}; push evaluator {decision}")
        # Remote tag names take precedence over inferred branch names; ambiguous names must be reported.
        g(work, 'push', '-q', 'origin', 'v1')
        case('short remote tag destination', 'git push origin wip:v1', 'allow', '')
        g(bare, 'update-ref', 'refs/heads/v1', g(work, 'rev-parse', 'main'))
        case('ambiguous remote destination', 'git push origin wip:v1', 'ask', 'ambiguous')
        # A newer remote default and a checked-out branch that is behind must not contaminate a clean source.
        g(peer, 'push', '-q', 'origin', 'main'); g(work, 'fetch', '-q', 'origin')
        g(work, 'branch', 'clean', 'origin/main')
        case('behind checked-out branch, clean source', 'git push origin clean:main', 'allow', '')
        case('behind HEAD with destination', 'git push origin HEAD:main', 'ask', 'behind origin', branch='unpublished')
        # Replay must cache by actual source and destination and fetch per chosen remote.
        replay_path = os.path.join(os.path.dirname(hook), 'replay.py')
        if not os.path.isfile(replay_path): raise RuntimeError('replay.py must be next to the hook under test')
        rspec = importlib.util.spec_from_file_location('push_test_replay', replay_path)
        replay = importlib.util.module_from_spec(rspec); rspec.loader.exec_module(replay)
        reset('clean')
        cmds = [{'cmd': cmd, 'cwd': work} for cmd in ('git push origin clean:main', 'git push origin main:main',
                                                     'git push backup wip:wip', 'git push origin wip:wip')]
        for fetch in (False, True):
            res = replay.summarize(hook, cmds, work, fetch=fetch)
            actual = [v[0] for v in res['memo'].values()]
            ok = actual == ['allow', 'ask', 'ask', 'ask'] and (not fetch or (res['remote_reads'] == 2 and res['fetches'] == 3))
            failed += not ok
            label = f"replay {'with fetch' if fetch else 'without fetch'}: sources/destinations cached separately"
            rows.append(dict(label=label, command='four pushes, two remotes', decision=str(actual), reason='', passed=ok))
            print(f"  {'✔' if ok else '✘'} {label}: {actual}; {res['fetches']} fetches")
        notices = replay.summarize(hook, [{'cmd': 'git push origin :main', 'cwd': work}], work)
        lines = replay.summary_lines(notices, 1, 30, examples=False)
        ok = not notices['counts'] and next(iter(notices['memo'].values())) == ('allow','') and not any('not judged' in line for line in lines)
        failed += not ok
        rows.append(dict(label='summary does not invent a prompt for silent deletion', command='git push origin :main',
                         decision='allow', reason='', passed=ok))
        print(f"  {'✔' if ok else '✘'} summary does not invent a prompt for silent deletion")
        g(work, 'remote', 'add', 'unrecorded', bare)
        g(work, 'update-ref', 'refs/remotes/unrecorded/main', g(work, 'rev-parse', 'origin/main'))
        unknown = replay.summarize(hook, [{'cmd':'git push unrecorded unpublished:newbranch', 'cwd':work}], work)
        decision, reason = next(iter(unknown['memo'].values()))
        ok = decision == 'ask' and 'no default branch' in reason
        failed += not ok
        rows.append(dict(label='offline unknown default baseline', command='git push unrecorded unpublished:newbranch',
                         decision=decision, reason=reason, passed=ok))
        print(f"  {'✔' if ok else '✘'} offline unknown default baseline: {decision}")
    print(f"{'✘' if failed else '✔'} push selftest: {len(rows)-failed}/{len(rows)} passed; {failed} wrong; no crashes; local bare remotes only")
    return failed, rows


if __name__ == '__main__':
    args = [arg for arg in sys.argv[1:] if arg != '--selftest']
    failed, rows = run(args[0] if args else None)
    if len(args) > 1: pathlib.Path(args[1]).write_text(json.dumps(rows, indent=2) + '\n')
    sys.exit(2 if failed else 0)
