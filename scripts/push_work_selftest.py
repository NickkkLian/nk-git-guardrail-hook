#!/usr/bin/env python3
"""Round-six invented ordinary lines and risky twins. All destinations are local bare fixtures."""
import argparse, contextlib, importlib.util, io, json, os, pathlib, shlex, subprocess, sys, tempfile, time


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def run(hook=None, output=None):
    sys.dont_write_bytecode = True
    root = pathlib.Path(__file__).resolve().parents[2]
    path = pathlib.Path(hook or pathlib.Path(__file__).with_name('guardrail.py')).resolve()
    mod = load(path, 'work_hook')
    baseline = root/'handback/baseline-6/guardrail.py'
    old = load(baseline, 'work_old') if baseline.exists() else None
    started = time.monotonic(); rows = []; failed = 0
    with tempfile.TemporaryDirectory(prefix='ordinary_') as tmp:
        d = pathlib.Path(tmp).resolve(); bare, w = d/'remote.git', d/'work'
        saved = dict(os.environ)
        os.environ.update(HOME=str(d), GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.com',
                          GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.com',
                          GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GUARDRAIL_CONFIG=str(d/'no-config'))
        def g(repo, *args):
            r = subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True)
            if r.returncode: raise RuntimeError(f'{args}: {r.stderr}')
            return r.stdout.strip()
        def answer(module, command):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try: module.check(command, str(w), module.load_config())
                except SystemExit: pass
            data = json.loads(buf.getvalue())['hookSpecificOutput'] if buf.getvalue() else {}
            assert data.get('permissionDecision') != 'allow', 'guard emitted approval'
            return data.get('permissionDecision','silent'), data.get('permissionDecisionReason','')
        def case(label, cmd, want='silent', needle='', ordinary=False):
            nonlocal failed
            before = (g(w,'rev-parse','HEAD'), (w/'.git/index').read_bytes(), g(w,'for-each-ref','--format=%(refname) %(objectname)'))
            got, why = answer(mod, cmd)
            after = (g(w,'rev-parse','HEAD'), (w/'.git/index').read_bytes(), g(w,'for-each-ref','--format=%(refname) %(objectname)'))
            prior = answer(old,cmd) if old else None
            ok = got==want and needle in why and before==after
            failed += not ok
            rows.append(dict(label=label,command=cmd.replace(str(d),'$FIXTURE'),decision=got,reason=why,
                             old=prior,ordinary=ordinary,passed=ok))
            print(f"  {'✔' if ok else '✘'} {label}: {got}" + (f' (want {want}: {needle}; {why})' if not ok else ''))
        try:
            d.mkdir(exist_ok=True); g(d,'init','-q','--bare','-b','main',str(bare)); g(d,'init','-q','-b','main',str(w))
            for n in range(40): (w/f'f{n}').write_text(str(n))
            g(w,'add','.'); g(w,'commit','-qm','base'); g(w,'remote','add','origin',str(bare)); g(w,'push','-qu','origin','main')
            base = g(w,'rev-parse','HEAD')
            g(w,'checkout','-qb','wip'); g(w,'rm','-qr','.'); g(w,'commit','-qm','wipe'); g(w,'checkout','-q','main')
            (w/'ahead').write_text('ahead'); g(w,'add','ahead'); g(w,'commit','-qm','one ahead')
            g(w,'branch','clean'); g(w,'fetch','-q','origin'); g(w,'symbolic-ref','refs/remotes/origin/HEAD','refs/remotes/origin/main')
            q = shlex.quote(str(w)); address = shlex.quote(str(bare)); ordinary = []
            for assign in (f'D={q}', f'D="{w}"', 'D="$HOME/work"', 'D=~/work', 'D=${HOME}/work', f'A={q}; D="$A"'):
                for op in ('git -C "$D" push origin main', 'cd "$D" && git push origin main'):
                    ordinary.append(('folder',assign+'; '+op))
            for key in ('user.name=t','user.email=t@example.com','core.hooksPath=/dev/null','core.sshCommand=ssh',
                        'core.askPass=/dev/null','core.editor=true','core.pager=cat','color.ui=false','color.branch=false',
                        'advice.pushUpdateRejected=false','credential.helper=','credential.useHttpPath=true',
                        'http.sslVerify=true','http.extraHeader=','gpg.program=gpg','commit.gpgSign=false',
                        'tag.gpgSign=false','i18n.commitEncoding=UTF-8','i18n.logOutputEncoding=UTF-8',
                        'protocol.file.allow=always','protocol.version=2','ssh.variant=ssh','push.gpgSign=false',
                        'core.quotePath=false'):
                ordinary.append(('config','git -c '+key+' push origin main'))
            ordinary.extend(('global',cmd) for cmd in ('git --no-optional-locks push origin main',
                'git -cuser.name=t push origin main','git -c user.name=t -c color.ui=false push origin main',
                f'git -c user.name=t -C {q} push origin main', f'git -C {q} -c user.name=t push origin main'))
            for dest in (address, '"'+str(bare)+'"', '../remote.git', 'file://'+str(bare)):
                if dest.startswith('file:'): g(w,'remote','add','filealias',dest)
                for ref in ('main','HEAD:main','refs/heads/main:refs/heads/main'):
                    ordinary.append(('address',f'git push {dest} {ref}'))
            for op in ('git pull --rebase','git pull --ff-only','git pull --no-rebase','git pull --ff-only origin main',
                       'git pull --rebase origin main','git merge --ff-only clean','git merge --no-edit clean',
                       'git merge --ff-only origin/main','git merge main','git -c user.name=t pull --ff-only'):
                ordinary.append(('history',op+' && git push origin main'))
            for body in ('git push origin main', 'git -c user.name=t push origin main',f'git -C {q} push origin main'):
                ordinary.append(('loop',f'for D in {q}; do '+body.replace(q,'"$D"')+'; done'))
            ordinary.append(('loop','for D in "$HOME/work"; do git -C "$D" push origin main; done'))
            ordinary.append(('loop',f'A={q}; for D in "$A"; do git -C "$D" push origin main; done'))
            ordinary.extend(('quoting',cmd) for cmd in (
                'git commit --allow-empty -m "say sh and don\'t parse prose" && git push origin main',
                'git commit --allow-empty -F - <<\'MSG\' && git push origin main\nsh\nDon\'t parse this.\nMSG',
                'cat <<\'MSG\'\ngit push origin wip:main\nMSG\ngit push origin main',
                'printf "%s" "$(printf \'a (b)\')"; git push origin main',
                'printf "%s" `printf \'a (b)\'`; git push origin main',
                'sh -c \'git push origin main\'',
                'bash <<\'SH\'\ngit push origin main\nSH',
                'echo "do not run `printf x`"; git push origin main'))
            ordinary.append(('quoting', 'git commit --allow-empty -F - <<\'MSG\' && git push origin main # sh\nDon\'t parse this data.\nMSG'))
            ordinary.append(('quoting', 'git commit --allow-empty -m \'mention `one\' -m "don\'t" -m \'two` text\' && git push origin main'))
            ordinary.append(('quoting', 'bash <<\'SH\'\npython3 <<\'PY\'\n# Don\'t parse another language as shell.\nprint("data")\nPY\ngit push origin main\nSH'))
            for n,(shape,cmd) in enumerate(ordinary,1):
                case(f'ordinary {n:02} {shape}',cmd,ordinary=True)
                # Same resolver shape sends the off-checkout wipe; require a measured wipe reason, not a generic ask.
                twin = cmd.replace('push origin main','push origin wip:main').replace('refs/heads/main:refs/heads/main','refs/heads/wip:refs/heads/main')
                if shape=='address': twin = cmd.rsplit(' ',1)[0]+' wip:main'
                if twin != cmd: case(f'twin {n:02} {shape}',twin,'ask','this push deletes 40 files')
            if old and hasattr(mod,'expand_literal'):
                def unjudged(*a, **kw): raise mod.PushNotJudged('projection disabled for ablation')
                def old_text(command):
                    command=old.strip_heredocs(command)
                    subs=old.re.findall(r'\$\([^()]*\)|`[^`]*`',command)
                    scripts=[m.group(1)[1:-1] for m in old.SHELL_ARG_RE.finditer(command)]
                    return old.push_shell_text(command)+'\n'+'\n'.join(old.push_shell_text(s[2:-1] if s.startswith('$(') else s[1:-1]) for s in subs)+'\n'+'\n'.join(scripts)
                ablations=[('folder','expand_literal',lambda *a:None),
                           ('config','harmless_config',lambda *a:False),
                           ('address','resolve_push',unjudged),
                           ('history','history_target',unjudged),
                           ('loop','literal_segments',lambda text,*a:mod.shell_segments(text,True)),
                           ('quoting','branch_executable',old_text)]
                for shape,name,disabled in ablations:
                    representative=next((r for r in rows if r['ordinary'] and r['label'].endswith(shape) and r['old'] and r['old'][0]=='ask' and
                                         (shape!='loop' or '$D' in r['command'])),None)
                    command=representative['command'].replace('$FIXTURE',str(d))
                    active=getattr(mod,name); setattr(mod,name,disabled)
                    try: got,reason=answer(mod,command)
                    finally: setattr(mod,name,active)
                    ok=got=='ask'; failed += not ok
                    print(f"  {'✔' if ok else '✘'} change-off {shape}: {got}; enabled silent")
            for label,cmd,needle in (
                ('unknown variable','git -C "$UNKNOWN" push origin main','shell expansion'),
                ('read binding',f'read D; git -C "$D" push origin main','shell expansion'),
                ('configuration home changes',f'HOME={shlex.quote(str(d))}; D="$HOME/work"; git -C "$D" push origin main','configuration search path'),
                ('future expanded repository',f'D={shlex.quote(str(d/"future"))}; mkdir "$D"; git -C "$D" init; git -C "$D" push origin main','future repository'),
                ('read loop binding',f'A={q}; read A; for D in "$A"; do git -C "$D" push origin main; done','shell expansion'),
                ('conditional binding',f'false && D={q}; git -C "$D" push origin main','shell expansion'),
                ('or binding',f'true || D={q}; git -C "$D" push origin main','shell expansion'),
                ('subshell binding',f'(D={q}); git -C "$D" push origin main','shell expansion'),
                ('unknown list', 'for D in "$UNSET"; do git -C "$D" push origin main; done','shell expansion'),
                ('config resolver','git -c push.default=current push','global option'),
                ('config tree','git -c core.worktree=/tmp push origin main','global option'),
                ('unmatched network','git push https://example.invalid/repo main','remote name'),
                ('unguarded pull','git pull --ff-only; git push origin main','successful &&'),
                ('unknown merge','git merge other && git push origin main','target'),
                ('substitution executes','echo "$(printf x; git push origin wip:main)"','not judged'),
                ('backtick executes','echo `printf x; git push origin wip:main`','not judged')):
                case(label,cmd,'ask',needle)
            case('parameter operator','D=${HOME:-/other}; git -C "$D" push origin main')
            # Hidden pushes ask rather than silently bypassing branch projection.
            case('command variable','G=git; $G push origin wip:main','ask','not judged')
            case('literal shell executes','eval \'git push origin wip:main\'','ask','not judged')
            case('resolved force option','F=--force; git push "$F" origin main','ask','force push')
            case('resolved plus refspec','R=+main:main; git push origin "$R"','ask','force push')
            case('resolved sweep option','A=-A; git add "$A" && git commit --allow-empty -m x && git push origin main','deny','git add -A')
            g(w,'config',f'url.{d}/elsewhere.pushInsteadOf',str(bare))
            case('direct address rewrite',f'git push {address} main','ask','could not be read')
            g(w,'config','--unset-all',f'url.{d}/elsewhere.pushInsteadOf')
            g(w,'config','remote.origin.push','wip:main')
            dry=g(w,'push','--dry-run','--porcelain',str(bare))
            assert 'refs/heads/main:refs/heads/main' in dry and 'refs/heads/wip:refs/heads/main' not in dry
            case('direct address default ignores named push refspec',f'git push {address}')
            case('named remote still uses configured wipe','git push origin','ask','this push deletes 40 files')
            g(w,'config','--unset-all','remote.origin.push')
            case('piped heredoc executes','cat <<\'SH\' | bash\ngit push origin wip:main\nSH','ask','this push deletes')
            # Ahead/behind fast-forward and divergent history are separate fixtures within this repository.
            g(w,'push','-q','origin','main')
            g(w,'checkout','-qb','later'); (w/'later').write_text('later'); g(w,'add','later'); g(w,'commit','-qm','later')
            later=g(w,'rev-parse','HEAD'); g(w,'push','-q','origin','later:main'); g(w,'checkout','-q','main')
            g(w,'fetch','-q','origin')
            case('behind without pull','git push origin main','ask','behind origin')
            case('behind scalar',f'D={q}; git -C "$D" push origin main','ask','behind origin')
            case('behind harmless config','git -c user.name=t push origin main','ask','behind origin')
            case('behind path address',f'git push {address} main','ask','behind ')
            case('behind literal loop',f'for D in {q}; do git -C "$D" push origin main; done','ask','behind origin')
            case('fast-forward pull','git pull --rebase && git push origin main')
            case('fast-forward merge','git merge --ff-only origin/main && git push origin main')
            case('fetch then fast-forward merge','git fetch origin && git merge --ff-only origin/main && git push origin main')
            case('fast-forward other pushed source remains behind','git pull --ff-only && git push origin clean:main','ask','behind origin')
            case('fast-forward plus commit stays unknown','git pull --ff-only && git commit -am x && git push origin main')
            g(w,'checkout','-qb','diverge','main'); (w/'diverge').write_text('diverge'); g(w,'add','diverge'); g(w,'commit','-qm','diverge')
            g(w,'checkout','-q','main')
            case('divergent merge','git merge diverge && git merge later && git push origin main','ask','divergent history')
            # A literal loop must inspect every value, including a later risky repository.
            g(w,'merge','--ff-only','-q','later')
            risky=d/'risky'; g(d,'clone','-q',str(bare),str(risky)); g(risky,'checkout','-q','main')
            g(risky,'rm','-qr','.'); g(risky,'commit','-qm','wipe')
            case('loop second repository wipes',f'for D in {q} {shlex.quote(str(risky))}; do git -C "$D" push origin main; done','ask','this push deletes')
            link=d/'work-link'; link.symlink_to(w,target_is_directory=True)
            case('resolved deletion through link',f'D={shlex.quote(str(link))}; rm "$D"/f*; git commit -am wipe && git push origin main','ask','deleting command')
            g(w,'checkout','-qb','nextwipe','later'); g(w,'rm','-qr','.'); g(w,'commit','-qm','next wipe')
            g(w,'push','-q','origin','nextwipe'); g(w,'checkout','-q','main')
            case('fast-forward merge sends wipe','git merge --ff-only nextwipe && git push origin main','ask','this push deletes')
            case('fast-forward pull sends wipe','git pull --ff-only origin nextwipe && git push origin main','ask','this push deletes')
            # Replay unavailable folders are separate, and accepted options never bypass offline isolation.
            replay = load(path.with_name('replay.py'), 'work_replay')
            records = [dict(cmd='git push origin main',cwd=str(d/'gone')),
                       dict(cmd='D="'+str(d/'gone')+'"; git -C "$D" push origin main',cwd=str(w)),
                       dict(cmd='git -c user.name=t push origin main',cwd=str(w)),
                       dict(cmd='git -C "$UNKNOWN" push origin main',cwd=str(w))]
            result = replay.summarize(str(path),records,str(w))
            ok=result['unreplayable']==2 and sum(result['unjudged'].values())==1 and result['fetches']==0
            failed += not ok
            print(f"  {'✔' if ok else '✘'} replay: {result['unreplayable']} unavailable, {dict(result['unjudged_reasons'])}, no network")
        finally:
            os.environ.clear(); os.environ.update(saved)
    if output:
        output=pathlib.Path(output); output.mkdir(parents=True,exist_ok=True)
        (output/'work-results.json').write_text(json.dumps(rows,indent=2)+'\n')
        lines=['# Invented ordinary lines: round 5 versus round 6','',
               'Local bare remote; main checked out, clean, one commit ahead. `$FIXTURE` is the throwaway root. Silent means no permission decision. Each ordinary source is main; successful pull/merge leaves it unchanged in this table. Risky twins and advancing histories are recorded in work-results.json.','',
               '| # | Shape | Command | Round 5 | Round 6 |','|---|---|---|---|---|']
        for n,row in enumerate([r for r in rows if r['ordinary']],1):
            command=row['command'].replace('|','\\|').replace('\n',r'\n')
            lines.append(f"| {n} | {row['label'].split()[-1]} | ``{command}`` | {row['old'][0] if row['old'] else 'unavailable'} | {row['decision']} |")
        (output/'ordinary-lines.md').write_text('\n'.join(lines)+'\n')
    print(f"{'✘' if failed else '✔'} work selftest: {len(rows)} lines plus replay; {failed} wrong; {time.monotonic()-started:.2f} seconds; local bare remotes only")
    return failed


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument("--selftest", action="store_true"); parser.add_argument('--hook'); parser.add_argument('--output')
    args=parser.parse_args(); sys.exit(2 if run(args.hook,args.output) else 0)
