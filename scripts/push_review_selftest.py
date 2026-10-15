#!/usr/bin/env python3
"""Outside-review regressions. Git's local dry-run is the refspec oracle. No network required."""
import argparse, contextlib, importlib.util, io, json, os, pathlib, shutil, subprocess, sys, tempfile, time


def run(hook=None, old=None, output=None):
    sys.dont_write_bytecode = True
    hook = os.path.abspath(hook or pathlib.Path(__file__).with_name('guardrail.py'))
    env = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.com',
               GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.com',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    rows, failures = [], 0
    spec=importlib.util.spec_from_file_location('review_hook',hook)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='push_review_') as tmp:
        env['GUARDRAIL_CONFIG'] = os.path.join(tmp, 'no-config')
        def g(repo, *args, check=True, input=None):
            r = subprocess.run(['git', '-C', str(repo), *args], input=input, capture_output=True, text=True, env=env)
            if check and r.returncode: raise RuntimeError(f'Git fixture failed: {args}: {r.stderr}')
            return r
        template = pathlib.Path(tmp, 'template'); template.mkdir()
        remote, seed, work = [template / n for n in ('origin.git', 'seed', 'work')]
        g(template, 'init', '-q', '--bare', '-b', 'main', str(remote))
        g(template, 'init', '-q', '-b', 'main', str(seed))
        for i in range(40): (seed / f'f{i}.txt').write_text(str(i))
        g(seed, 'add', '.'); g(seed, 'commit', '-qm', 'base'); g(seed, 'remote', 'add', 'origin', str(remote))
        g(seed, 'push', '-q', 'origin', 'main', 'main:stale', 'main:clean2', 'main:wipetracked')
        g(template, 'clone', '-q', str(remote), str(work))
        (work / 'new.txt').write_text('x'); g(work, 'add', '.'); g(work, 'commit', '-qm', 'clean')
        g(work, 'branch', '--track', 'stale', 'origin/stale')
        g(work, 'checkout', '-q', '--track', '-b', 'wipetracked', 'origin/wipetracked')
        g(work, 'rm', '-qr', '.'); g(work, 'commit', '-qm', 'wipe')
        g(work, 'checkout', '-q', '--no-track', '-b', 'wip', 'origin/main')
        g(work, 'rm', '-qr', '.'); g(work, 'commit', '-qm', 'wipe')
        g(work, 'checkout', '-q', 'main'); g(work, 'tag', 'vok')
        g(seed, 'checkout', '-qb', 'stale')
        for i in range(2):
            (seed / f'r{i}.txt').write_text('x'); g(seed, 'add', '.'); g(seed, 'commit', '-qm', 'remote only')
        g(seed, 'push', '-q', 'origin', 'stale')

        def fixture(branch='main'):
            d = pathlib.Path(tmp, f'case{len(rows)}'); shutil.copytree(template, d)
            w, b = d/'work', d/'origin.git'
            g(w, 'remote', 'set-url', 'origin', str(b)); g(w, 'checkout', '-q', branch)
            return d, w, b

        def entry(path, command, cwd, use_env=env):
            event = json.dumps({'tool_name':'Bash', 'tool_input':{'command':command}, 'cwd':str(cwd)})
            started = time.monotonic()
            r = subprocess.run([sys.executable, str(path)], input=event, capture_output=True, text=True, env=use_env, timeout=20)
            elapsed=time.monotonic()-started
            if r.returncode or r.stderr: raise RuntimeError(f'hook process failed: {r.returncode}, {r.stderr}')
            data = json.loads(r.stdout)['hookSpecificOutput'] if r.stdout.strip() else {}
            if str(path) == hook:
                saved=dict(os.environ); os.environ.update(use_env)
                buf=io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        try: module.check(command,str(cwd),module.load_config())
                        except SystemExit: pass
                finally: os.environ.clear(); os.environ.update(saved)
                direct=json.loads(buf.getvalue())['hookSpecificOutput'] if buf.getvalue().strip() else {}
                assert direct == data, 'direct check and hook entry point differ'
            return data.get('permissionDecision', 'silent'), data.get('permissionDecisionReason',''), r.stdout, elapsed

        def truth(w, b, args, before=''):
            # Truth is isolated: its fetches must not make objects available to the hook being tested.
            oracle = w.parent/'oracle'; shutil.copytree(w, oracle)
            if before:
                prior=subprocess.run(['/bin/sh','-c',before],cwd=oracle,capture_output=True,text=True,env=env)
                if prior.returncode: raise RuntimeError('oracle could not run the prior Git mutation: '+prior.stderr)
            r = g(oracle, 'push', '--dry-run', '--porcelain', *args, check=False)
            remote_name=next((arg for arg in args if not arg.startswith('-')),'origin')
            remote_path=g(oracle,'remote','get-url',remote_name).stdout.strip()
            updates, risk = [], 'clean'
            for line in r.stdout.splitlines():
                fields = line.split('\t')
                if len(fields) < 3 or ':' not in fields[1]: continue
                src, dst = fields[1].split(':', 1); updates.append((src, dst))
                if not src or not dst.startswith('refs/heads/'): continue
                local = g(oracle, 'rev-parse', src).stdout.strip()
                dest = g(remote_path, 'rev-parse', '--verify', dst, check=False)
                exists = dest.returncode == 0
                if not exists: dest = g(remote_path, 'rev-parse', '--verify', 'HEAD', check=False)
                if dest.returncode: continue
                oid = dest.stdout.strip()
                g(oracle, 'fetch', '-q', '--no-tags', remote_name, oid)
                n = int(g(oracle, 'rev-list', '--count', f'{local}..{oid}').stdout)
                if exists and n: risk = 'behind'; continue
                base = g(oracle, 'merge-base', oid, local, check=False)
                diff = g(oracle, 'diff', '--no-renames', '--name-status', base.stdout.strip() if base.returncode == 0 else oid, local)
                statuses = [line.split('\t')[0] for line in diff.stdout.splitlines()]
                deleted = statuses.count('D'); added = len(statuses)-deleted
                if risk != 'behind' and deleted >= 20 and deleted > 3*added: risk = 'wipe'
            return risk, updates, r.returncode

        def record(label, command, result, ok, oracle=None, previous=None):
            nonlocal failures
            failures += not ok
            rows.append(dict(label=label, command=command, decision=result[0], reason=result[1],
                             seconds=round(result[3],3), passed=bool(ok), truth=oracle, old=previous))
            print(f"  {'✔' if ok else '✘'} {label}: {result[0]}" + (f' (oracle {oracle})' if oracle else ''))

        def case(label, command, args=None, branch='main', prepare=None, expect=None, specific='', named=False, legacy=False, outside=False, before=''):
            d, w, b = fixture(branch)
            if prepare: prepare(d,w,b)
            command = command.replace('$WORK', str(w)).replace('$ROOT', str(d))
            cwd = d if outside or label == 'pushd selects repository' else w
            oracle = truth(w,b,args,before) if args is not None else None
            previous = None
            if old:
                previous_work=d/'previous'; shutil.copytree(w,previous_work)
                previous = entry(old,command.replace(str(w),str(previous_work)),d if cwd==d else previous_work)[:2]
            result = entry(hook,command,cwd)
            want = expect or ('ask' if oracle and oracle[0] != 'clean' else 'silent')
            ok = result[0] == want and result[0] != 'allow'
            if specific: ok &= specific in result[1]
            if want == 'silent': ok &= result[2] == ''
            if named and oracle:
                ok &= any((f"Source {src.removeprefix('refs/heads/')} → origin/{dst.removeprefix('refs/heads/')}" + ".") in result[1]
                          for src,dst in oracle[1] if src and dst.startswith('refs/heads/'))
            if legacy and old: ok &= previous[0] == 'ask'
            record(label,command,result,ok,oracle,previous)

        for label, cmd, args in [
            ('never approve deletion chain','git push origin :clean2; rm -rf build; ./deploy.sh production',['origin',':clean2']),
            ('never approve tags','git push origin vok',['origin','vok']),
            ('never approve delete option','git push origin --delete clean2',['origin','--delete','clean2']),
            ('never approve new branch','git push origin main:brandnew',['origin','main:brandnew']),
            ('tag shorthand','git push origin tag vok',['origin','tag','vok']),
        ]: case(label,cmd,args)
        case('never approve non-repository','git push origin main',outside=True,expect='silent')
        # Every wrapper the outside check names; compare the old hook on both risky histories.
        wrappers = ['time ', 'command ', 'nohup ', 'nice ', 'exec ', '! ', 'if true; then ',
                    'true && { ', 'for r in origin; do ', 'xargs ', 'timeout 60 ', 'caffeinate -i ',
                    '\\', 'GIT_SSH_COMMAND="ssh -i key" ', 'VAR="a b" ', 'echo start; time ']
        for branch in ('wipetracked','stale'):
            for prefix in wrappers:
                suffix = '; fi' if prefix.startswith('if ') else '; }' if '{' in prefix else '; done' if prefix.startswith('for ') else ' < /dev/null' if prefix=='xargs ' else ''
                command = prefix+'git push'+suffix
                case(f'wrapper {prefix.strip()} / {branch}',command,['origin',branch],branch=branch,legacy=True)
        for prefix in wrappers:
            suffix = '; fi' if prefix.startswith('if ') else '; }' if '{' in prefix else '; done' if prefix.startswith('for ') else ' < /dev/null' if prefix=='xargs ' else ''
            case('wrapped explicit wipe '+prefix.strip(),prefix+'git push origin wip:main'+suffix,['origin','wip:main'])
        case('loop supplies remote variable','for r in origin; do git push $r; done',['origin','wipetracked'],
              branch='wipetracked',expect='ask',specific='this push deletes 40 files',legacy=True)
        case('pushd selects repository','pushd "$WORK" && git push origin wip:main',['origin','wip:main'])
        case('pushd old asking form','pushd "$WORK" && git push',['origin','wipetracked'],branch='wipetracked',legacy=True)
        case('push alias','git p origin wip:main',['origin','wip:main'],prepare=lambda d,w,b:g(w,'config','alias.p','push'))
        case('push alias with global options','git p origin wip:main',['origin','wip:main'],
             prepare=lambda d,w,b:g(w,'config','alias.p','-c push.default=current push'),specific='alias includes global options')
        case('alias defined earlier in the line','git config alias.p push && git p origin wip:main',['origin','wip:main'],
             before='git config alias.p push',expect='ask',specific='this push deletes')
        for suffix in [' 2>&1 | tail -3',' 2>&1',' 2>/dev/null',' >/dev/null 2>&1',' > /dev/null'," <<< ''",' # note', ' | cat']:
            case('clean redirection/comment '+suffix, 'git push origin main'+suffix,['origin','main'])
            case('wipe redirection/comment '+suffix, 'git push origin wip:main'+suffix,['origin','wip:main'],
                 named=True,specific='this push deletes 40 files')
        case('implicit push with redirection','git push 2>&1 | tail -3',['origin','wipetracked'],branch='wipetracked',named=True)
        def numeric_branch(d,w,b):
            g(w,'branch','2','wip'); g(b,'update-ref','refs/heads/2',g(b,'rev-parse','main').stdout.strip())
        case('quoted numeric branch is not a file descriptor','git push origin "2"> /dev/null',['origin','2'],
             prepare=numeric_branch,named=True,specific='this push deletes 40 files')
        def empty(d,w,b):
            e=d/'empty.git'; g(d,'init','-q','--bare',str(e)); g(w,'remote','add','empty',str(e))
        case('empty remote','git push -u empty main',['empty','-u','main'],prepare=empty,expect='silent')
        case('dangling HEAD existing destination','git push origin main',['origin','main'],
             prepare=lambda d,w,b:g(b,'symbolic-ref','HEAD','refs/heads/nope'))
        case('dangling HEAD new destination','git push origin main:newbranch',['origin','main:newbranch'],
             prepare=lambda d,w,b:g(b,'symbolic-ref','HEAD','refs/heads/nope'),expect='ask',specific='no default branch')
        case('same-name wipe names pair','git push origin wipetracked',['origin','wipetracked'],named=True)
        case('same-name stale names pair and fetches','git push origin stale',['origin','stale'],named=True,specific='2 commit(s)')
        case('default branch named in ask','git push origin wip:newbranch',['origin','wip:newbranch'],specific='default branch main')
        for command, branch in [('git checkout wipetracked && git push','main'),
                                ('git checkout main && git push','wipetracked'),
                                ('git commit -m wipe && git push','main'),
                                ('git add -u && git commit -m wipe && git push','main'),
                                ('git commit -am wipe && git push','main'),
                                ('git pull --rebase origin stale && git push origin stale','stale')]:
            def prepare_mutation(d,w,b):
                if 'commit' in command:
                    if '-am' in command or 'git add -u' in command:
                        for p in w.glob('f*.txt'): p.unlink()
                    else: g(w,'rm','-q','--',*[p.name for p in w.glob('f*.txt')])
            expectation = 'silent' if 'pull' in command or command.startswith('git checkout main') else None
            detail = '' if expectation=='silent' else 'this push deletes 40 files'
            case('prior mutation '+command,command,['origin','stale'] if 'pull' in command else ['origin'],
                 branch=branch,prepare=prepare_mutation,expect=expectation,specific=detail,before=command.rsplit('&&',1)[0])
        def subdir_commit(d,w,b):
            (w/'sub').mkdir(); g(w,'rm','-q','--',*[p.name for p in w.glob('f*.txt')])
        case('mutation in subdirectory shares repository','git -C sub commit -m wipe && git push',['origin'],
             prepare=subdir_commit,expect='ask',specific='this push deletes 40 files',before='git -C sub commit -m wipe')
        # Refs after a judgement must match the old hook's narrow fetch, not the broad fetch being replaced.
        d,w,b=fixture(); g(w,'update-ref','refs/remotes/origin/keepme','main')
        old_work=d/'old-work'; shutil.copytree(w,old_work)
        if old: entry(old,'git push origin main',old_work)
        before=g(old_work,'for-each-ref','--format=%(refname) %(objectname)').stdout
        result=entry(hook,'git push origin main',w)
        after=g(w,'for-each-ref','--format=%(refname) %(objectname)').stdout
        record('refs equal old judgement; no prune','git push origin main',result,after==before)
        d,w,b=fixture('stale'); g(w,'update-ref','refs/remotes/origin/keepme','main')
        old_work=d/'old-work'; shutil.copytree(w,old_work)
        if old: entry(old,'git push origin stale',old_work)
        else: g(old_work,'fetch','-q','origin','stale')
        before=g(old_work,'for-each-ref','--format=%(refname) %(objectname)').stdout
        result=entry(hook,'git push origin stale',w)
        after=g(w,'for-each-ref','--format=%(refname) %(objectname)').stdout
        record('refs equal old judgement after destination advances','git push origin stale',result,after==before)
        d,w,b=fixture()
        oid=g(b,'rev-parse','main').stdout.strip()
        g(b,'update-ref','--stdin',input=''.join(f'update refs/tags/remote{i} {oid}\n' for i in range(3000)))
        refs_before=g(w,'for-each-ref','--format=%(refname) %(objectname)').stdout
        result=entry(hook,'git push origin main',w)
        refs_after=g(w,'for-each-ref','--format=%(refname) %(objectname)').stdout
        record('no remote tag imports or private refs','git push origin main',result,refs_before==refs_after)
        d,w,b=fixture(); shallow=d/'shallow'
        g(d,'clone','-q','--depth','1','--single-branch','file://'+str(b),str(shallow))
        refs_before=g(shallow,'for-each-ref','--format=%(refname) %(objectname)').stdout
        result=entry(hook,'git push origin main',shallow)
        refs_after=g(shallow,'for-each-ref','--format=%(refname) %(objectname)').stdout
        record('shallow clone remains single branch','git push origin main',result,refs_before==refs_after)
        d,w,b=fixture()
        oid=g(w,'rev-parse','main').stdout.strip()
        g(w,'update-ref','--stdin',input=''.join(f'update refs/heads/many{i} {oid}\n' for i in range(310)))
        result=entry(hook,'git push --all origin',w)
        record('314-branch bound and compact answer','git push --all origin',result,
               result[0]=='ask' and result[3]<9.5 and len(result[2])<1600)
        # A hanging git transport is simulated by a child process; no loopback/network permission is needed.
        d,w,b=fixture(); shim=d/'bin'; shim.mkdir(); realgit=shutil.which('git')
        shim_git=shim/'git'
        shim_git.write_text(f'#!{sys.executable}\nimport os,sys,time\nif "fetch" in sys.argv or "ls-remote" in sys.argv: time.sleep(30)\nos.execv({realgit!r}, [{realgit!r}]+sys.argv[1:])\n')
        shim_git.chmod(0o755)
        result=entry(hook,'git push origin main',w,dict(env,PATH=str(shim)+os.pathsep+env['PATH']))
        record('total deadline with plain timeout','git push origin main',result,
               result[0]=='ask' and result[3]<9.5 and 'time limit' in result[1] and str(w) not in result[1] and 'Command [' not in result[1])
        replay_path=pathlib.Path(hook).with_name('replay.py')
        spec=importlib.util.spec_from_file_location('review_replay',replay_path)
        replay=importlib.util.module_from_spec(spec); spec.loader.exec_module(replay)
        d,w,b=fixture()
        res=replay.summarize(hook,[{'cmd':'git push --mystery origin main','cwd':str(w)}],str(w))
        lines=replay.summary_lines(res,1,30)
        count_lines=[line for line in lines if line.strip().startswith('1 ') and ('not judged' in line or 'stopped for' in line)]
        record('summary counts unjudged once','git push --mystery origin main',('ask','\n'.join(lines),'',0),len(count_lines)==1)
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            try: module.decide('allow','an internal clean result')
            except SystemExit: pass
        record('decision emitter cannot approve any path','decide(allow)',('silent' if not buf.getvalue() else 'allow','',buf.getvalue(),0),not buf.getvalue())
        real=module.subprocess
        class NoGit:
            def run(self,*a,**kw): raise AssertionError('non-push command started Git')
        module.subprocess=NoGit()
        try:
            with contextlib.redirect_stdout(io.StringIO()): module.check('git status; git diff; npm test',str(w),dict(module.DEFAULTS))
        finally: module.subprocess=real
        record('non-push commands start no Git subprocesses','git status; git diff; npm test',('silent','','',0),True)
    print(f"{'✘' if failures else '✔'} review push selftest: {len(rows)-failures}/{len(rows)} passed; {failures} wrong; local remotes only")
    if output: pathlib.Path(output).write_text(json.dumps(rows,indent=2)+'\n')
    return failures, rows


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true"); ap.add_argument('--hook'); ap.add_argument('--old'); ap.add_argument('--out')
    a=ap.parse_args(); failed,_=run(a.hook,a.old,a.out); sys.exit(2 if failed else 0)
