#!/usr/bin/env python3
"""Independent everyday-line and projected-commit regressions. Local bare remotes only."""
import argparse, contextlib, importlib.util, io, json, os, pathlib, shutil, subprocess, sys, tempfile, time

EVERYDAY = [
    'git add f01.txt && git commit -m "msg" && git push',
    'git commit -m x && git push origin main',
    'git commit -am x && git push',
    'git pull --rebase && git push',
    'git fetch && git push',
    'git checkout -b feature && git push -u origin feature',
    'git tag v9 && git push origin v9',
    'git branch -d clean2 && git push',
    'git config user.name t && git push',
    'git stash pop; git push',
    'git status && git push',
    'git log -1 --oneline && git push',
    'git diff --stat && git push',
    'git push origin main --no-verify',
    'git push -q',
    'git push --verbose',
    'git push --porcelain',
    'git push --atomic origin main',
    'git push && gh pr create --fill',
    'git push -u origin HEAD',
    'git push --set-upstream origin $(git branch --show-current)',
    'git push origin "$(git rev-parse --abbrev-ref HEAD)"',
    'git push origin HEAD:refs/heads/main',
    'npm version patch && git push --follow-tags',
    'git push 2>&1 | tail -5',
    'git push origin main && git push origin --tags',
    'git remote -v && git push',
    'git add f01.txt && git commit -m x && git push origin HEAD',
    'git show --stat HEAD && git push',
    'git restore --staged . && git push',
    'git rm --cached -q f01.txt; git push',
    'git mv f01.txt g01.txt && git commit -m mv && git push',
]


def run(hook=None, old=None, output=None, fast=False, closing=False, linked=False, final=False):
    started = time.monotonic(); sys.dont_write_bytecode = True
    hook = str(pathlib.Path(hook or pathlib.Path(__file__).with_name('guardrail.py')).resolve())
    spec = importlib.util.spec_from_file_location('line_hook', hook)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    env = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.com',
               GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.com',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    rows, failed = [], 0
    with tempfile.TemporaryDirectory(prefix='push_lines_') as tmp:
        tmp = pathlib.Path(tmp)
        if linked:
            alias = tmp/'linked'; alias.symlink_to(tmp.resolve(), target_is_directory=True); tmp = alias
            assert str(tmp) != str(tmp.resolve()), 'linked fixture must use a different path spelling'
            print('Fixture paths reached through a symbolic link.')
        template = tmp/'template'; template.mkdir()
        bare, seed, work = [template/n for n in ('origin.git', 'seed', 'work')]
        env['GUARDRAIL_CONFIG'] = str(tmp/'no-config')
        def g(repo, *args, check=True):
            r = subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,env=env)
            if check and r.returncode: raise RuntimeError(f'fixture Git failed: {args}: {r.stderr}')
            return r
        g(template,'init','-q','--bare','-b','main',str(bare))
        g(template,'init','-q','-b','main',str(seed))
        for i in range(1,41): (seed/f'f{i:02}.txt').write_text(f'{i}\n')
        g(seed,'add','.'); g(seed,'commit','-qm','base'); g(seed,'remote','add','origin',str(bare))
        g(seed,'push','-q','origin','main','main:clean2','main:wipetracked','main:stale')
        g(template,'clone','-q',str(bare),str(work))
        g(work,'branch','clean2','origin/clean2')
        g(work,'checkout','-q','--track','-b','wipetracked','origin/wipetracked')
        g(work,'rm','-q','--',*[f'f{i:02}.txt' for i in range(1,41)]); g(work,'commit','-qm','wipe')
        g(work,'checkout','-q','main'); (work/'new-main.txt').write_text('clean\n')
        g(work,'add','new-main.txt'); g(work,'commit','-qm','one ahead')
        g(work,'branch','clean','main'); g(work,'branch','wip','wipetracked')
        g(work,'tag','vok')

        def snapshot(w):
            return (g(w,'rev-parse','HEAD').stdout, (w/'.git/index').read_bytes(),
                    {str(p.relative_to(w)):p.read_bytes() for p in w.rglob('*') if p.is_file() and '.git' not in p.relative_to(w).parts})

        def entry(path, cmd, w, cfg=None, cwd=None):
            use_env = dict(env)
            if cfg:
                config = w.parent/'config.json'; config.write_text(json.dumps(cfg)); use_env['GUARDRAIL_CONFIG']=str(config)
            before = snapshot(w)
            r = subprocess.run([sys.executable,path],input=json.dumps({'tool_name':'Bash','tool_input':{'command':cmd},'cwd':str(cwd or w)}),
                               capture_output=True,text=True,env=use_env,timeout=12)
            if r.returncode or r.stderr: raise RuntimeError(f'hook failed: {r.returncode}: {r.stderr}')
            data = json.loads(r.stdout)['hookSpecificOutput'] if r.stdout else {}
            if path == hook:
                saved = dict(os.environ); os.environ.update(use_env); buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        try: mod.check(cmd,str(cwd or w),mod.load_config())
                        except SystemExit: pass
                finally: os.environ.clear(); os.environ.update(saved)
                direct = json.loads(buf.getvalue())['hookSpecificOutput'] if buf.getvalue() else {}
                assert direct == data, 'direct check and entry point disagree'
                assert snapshot(w) == before, 'projection changed HEAD/index/worktree'
            return data.get('permissionDecision','silent'),data.get('permissionDecisionReason',''),r.stdout

        def oracle(w, args, prior):
            o = w.parent/'oracle'; shutil.copytree(w,o)
            # Only explicit, fixture-owned Git commands are executed; no push or arbitrary script is run.
            for command in prior:
                if command[0] == '$remove':
                    for name in command[1:]:
                        target = o/name
                        if target.is_dir(): shutil.rmtree(target)
                        elif target.exists(): target.unlink()
                else: g(o,*command,check=False)
            r = g(o,'push','--dry-run','--porcelain',*args,check=False)
            updates = []
            risk, deleted = 'clean', 0
            remote = g(o,'remote','get-url','origin').stdout.strip()
            for line in r.stdout.splitlines():
                fields = line.split('\t')
                if len(fields)<3 or ':' not in fields[1]: continue
                src,dst = fields[1].split(':',1); updates.append([src,dst])
                if not src or not dst.startswith('refs/heads/'): continue
                parent = g(o,'rev-parse',src).stdout.strip()
                target = g(remote,'rev-parse','--verify',dst,check=False)
                exists = target.returncode == 0
                if not exists: target = g(remote,'rev-parse','--verify','HEAD',check=False)
                if target.returncode: continue
                oid = target.stdout.strip(); g(o,'fetch','-q','--no-tags','origin',oid)
                if exists and int(g(o,'rev-list','--count',parent+'..'+oid).stdout): risk='behind'; continue
                base = g(o,'merge-base',oid,parent,check=False)
                diff = g(o,'diff','--no-renames','--name-status','-z',base.stdout.strip() if base.returncode==0 else oid,parent)
                statuses = diff.stdout.split('\0')[0:-1:2]; d=statuses.count('D'); a=len(statuses)-d
                if risk != 'behind' and d>=20 and d>3*a: risk='wipe'; deleted=d
            return {'risk':risk,'deleted':deleted,'updates':updates,'git_exit':r.returncode}

        def case(label, cmd, args=('origin','main'), prior=(), setup=None, want=None, text='', branch='main', cfg=None, outside=False, cwd=None):
            nonlocal failed
            if closing and not label.startswith('C'): return
            if final and not label.startswith('F'): return
            d = tmp/f'case{len(rows)}'; shutil.copytree(template,d); w,b = d/'work',d/'origin.git'
            g(w,'remote','set-url','origin',str(b)); g(w,'checkout','-q',branch)
            if setup: setup(w,b)
            cmd = cmd.replace('$WORK',str(w))
            truth = oracle(w,list(args),prior)
            previous = None
            if old:
                p=d/'old'; shutil.copytree(w,p)
                previous=entry(str(pathlib.Path(old).resolve()),cmd.replace(str(w),str(p)),p,cfg,cwd=d if outside else p/cwd if cwd else None)[:2]
            got,why,stdout=entry(hook,cmd,w,cfg,cwd=d if outside else w/cwd if cwd else None)
            expected = want or ('ask' if truth['risk']!='clean' else 'silent')
            needle = text or (f"this push deletes {truth['deleted']} files" if truth['risk']=='wipe' and expected!='silent' else '')
            ok = got == expected and got != 'allow' and needle in why and (got!='silent' or stdout=='')
            failed += not ok
            rows.append(dict(label=label,command=cmd,decision=got,reason=why,old=previous,truth=truth,passed=ok))
            print(f"  {'✔' if ok else '✘'} {label}: {got}; Git {truth['risk']}" + (f' (want {expected}, {needle!r})' if not ok else ''))

        fast_ids = {2,3,21}
        for n,cmd in enumerate(EVERYDAY,1):
            if fast and n not in fast_ids: continue
            prior=[]; args=['origin','main']
            if n in (1,28): prior=[['add','f01.txt'],['commit','-m','msg']]
            elif n==2: prior=[['commit','-m','x']]
            elif n==3: prior=[['commit','-am','x']]
            elif n==4: prior=[['pull','--rebase']]
            elif n==5: prior=[['fetch']]
            elif n==6: prior=[['checkout','-b','feature']]; args=['-u','origin','feature']
            elif n==7: prior=[['tag','v9']]; args=['origin','v9']
            elif n==8: prior=[['branch','-d','clean2']]
            elif n==9: prior=[['config','user.name','t']]
            elif n==10: prior=[['stash','pop']]
            elif n==30: prior=[['restore','--staged','.']]
            elif n==31: prior=[['rm','--cached','-q','f01.txt']]
            elif n==32: prior=[['mv','f01.txt','g01.txt'],['commit','-m','mv']]
            case(f'V{n:02}',cmd,args,prior,want='silent')

        def staged(w,b): g(w,'rm','-q','--',*[f'f{i:02}.txt' for i in range(1,41)])
        def removed(w,b):
            for p in w.glob('f*.txt'): p.unlink()
        case('E01 index wipe','git commit -m wipe && git push',prior=[['commit','-m','wipe']],setup=staged)
        case('E02 tracked working-tree wipe','git commit -am wipe && git push',prior=[['commit','-am','wipe']],setup=removed)
        if not fast:
            case('E03 add-u wipe','git add -u && git commit -m wipe && git push',prior=[['add','-u'],['commit','-m','wipe']],setup=removed)
            case('E04 add-all wipe','git add -A && git commit -m wipe && git push',prior=[['add','-A'],['commit','-m','wipe']],setup=removed,cfg={'add_all':'off'})
            case('add-dot wipe','git add . && git commit -m wipe && git push',prior=[['add','.'],['commit','-m','wipe']],setup=removed,cfg={'add_all':'off'})
            names=[f'f{i:02}.txt' for i in range(1,41)]
            case('explicit staging paths wipe','git add -- '+' '.join(names)+' && git commit -m wipe && git push',prior=[['add','--',*names],['commit','-m','wipe']],setup=removed)
            case('only one deletion staged','git add f01.txt && git commit -m one && git push',prior=[['add','f01.txt'],['commit','-m','one']],setup=removed)
            case('index ignores unstaged wipe','git commit -m x && git push',prior=[['commit','-m','x']],setup=removed)
            def add_new(w,b):
                removed(w,b)
                for i in range(20): (w/f'new{i}.txt').write_text('new\n')
            case('new files count after add-all','git add -A && git commit -m replace && git push',prior=[['add','-A'],['commit','-m','replace']],setup=add_new,cfg={'add_all':'off'})
            case('commit source distinct from pushed source','git commit -m wipe && git push origin clean',args=['origin','clean'],prior=[['commit','-m','wipe']],setup=staged)
            case('new branch inherits proposed wipe','git commit -m wipe && git checkout -b feature && git push -u origin feature',
                 args=['-u','origin','feature'],prior=[['commit','-m','wipe'],['checkout','-b','feature']],setup=staged)
            case('resetting current branch before commit needs future index','git checkout -B main wip && git commit --allow-empty -m x && git push',
                 prior=[['checkout','-B','main','wip'],['commit','--allow-empty','-m','x']],want='ask',text='future index')
            def intent_wipe(w,b):
                staged(w,b); names=[f'intent{i}.txt' for i in range(30)]
                for name in names: (w/name).write_text('new\n')
                g(w,'add','-N','--',*names)
            case('intent-to-add cannot hide an index wipe','git commit -m wipe && git push',prior=[['commit','-m','wipe']],setup=intent_wipe)
            case('commit-a stages intent-to-add working files','git commit -am replace && git push',prior=[['commit','-am','replace']],setup=intent_wipe)
            case('staged restore clears intent before commit-a','git restore --staged . && git commit -am wipe && git push',
                 prior=[['restore','--staged','.'],['commit','-am','wipe']],setup=intent_wipe)
            def flags(w,b): g(w,'update-index','--assume-unchanged','f01.txt')
            case('special working-tree index flags are explicit','git commit -am x && git push',
                 prior=[['commit','-am','x']],setup=flags)
            case('commit clustered short options','git commit -qam x && git push',prior=[['commit','-qam','x']],setup=removed)
            case('commit attached message','git commit -amwipe && git push',prior=[['commit','-amwipe']],setup=removed)
            case('tracked staging long option','git add --update && git commit --message=wipe && git push',prior=[['add','--update'],['commit','--message=wipe']],setup=removed)
            case('rm then commit projects index','git rm -r -- f01.txt f02.txt && git commit -m rm && git push',prior=[['rm','-r','--','f01.txt','f02.txt'],['commit','-m','rm']])
            names=[f'f{i:02}.txt' for i in range(1,41)]
            case('rm then add-all cannot resurrect files','git rm -- '+' '.join(names)+' && git add -A && git commit -m wipe && git push',
                 prior=[['rm','--',*names],['add','-A'],['commit','-m','wipe']],cfg={'add_all':'off'})
            def restored_staged(w,b):
                originals={p.name:p.read_bytes() for p in w.glob('f*.txt')}; staged(w,b)
                for name,data in originals.items(): (w/name).write_bytes(data)
            case('plain commit uses staged deletions despite restored files','git commit -m wipe && git push',prior=[['commit','-m','wipe']],setup=restored_staged)
            case('add without paths does not stage restored files','git add && git commit -m wipe && git push',prior=[['add'],['commit','-m','wipe']],setup=restored_staged)
            case('add-all restores deleted index entries','git add -A && git commit -m restored && git push',prior=[['add','-A'],['commit','-m','restored']],setup=restored_staged,cfg={'add_all':'off'})
            def ignored_new(w,b):
                removed(w,b); (w/'.gitignore').write_text('*.tmp\n')
                for i in range(30): (w/f'ignored{i}.tmp').write_text('ignored\n')
            case('ignored files cannot hide wipe','git add -A && git commit -m wipe && git push',prior=[['add','-A'],['commit','-m','wipe']],setup=ignored_new,cfg={'add_all':'off'})
            case('config user with scope flag','git config --local user.name t && git commit -m x && git push',prior=[['config','--local','user.name','t'],['commit','-m','x']])
            case('staging alone sends committed source','git add -u && git push',setup=removed,prior=[['add','-u']])
            def advanced(w,b):
                peer=w.parent/'peer'; g(w.parent,'clone','-q',str(b),str(peer))
                (peer/'remote.txt').write_text('remote\n'); g(peer,'add','remote.txt'); g(peer,'commit','-qm','remote only'); g(peer,'push','-q','origin','main')
            case('proposed commit cannot cure divergent history','git commit --allow-empty -m x && git push',
                 prior=[['commit','--allow-empty','-m','x']],setup=advanced,want='ask',text='1 commit(s) behind origin')
            case('checkout wipe branch','git checkout wipetracked && git push',args=['origin','wipetracked'],prior=[['checkout','wipetracked']])
            case('switch clean branch','git switch main && git push',prior=[['switch','main']],branch='wipetracked')
            case('@ source','git push origin @',args=['origin','@'],branch='wipetracked')
            case('@ explicit destination','git push origin @:main',args=['origin','@:main'],branch='wipetracked')
            case('known branch substitution reads wipe','git push origin $(git branch --show-current)',args=['origin','wipetracked'],branch='wipetracked')
            case('known quoted branch substitution reads wipe','git push origin "$(git rev-parse --abbrev-ref HEAD)"',args=['origin','wipetracked'],branch='wipetracked')
            def branch_markers(w,b):
                g(w,'branch','__GUARDRAIL_CURRENT_BRANCH__','wip')
                g(w,'branch','__PUSH_SUB_0__main','wip'); g(w,'branch','mainmain','main')
            case('literal branch name cannot become a substitution','git push origin __GUARDRAIL_CURRENT_BRANCH__:main',
                 args=['origin','__GUARDRAIL_CURRENT_BRANCH__:main'],setup=branch_markers)
            case('literal prefix survives current-branch substitution','git push origin __PUSH_SUB_0__$(git branch --show-current):main',
                 args=['origin','__PUSH_SUB_0__main:main'],setup=branch_markers)

        for label,cmd in [
            ('command-word substitution','$(which git) push'),
            ('backtick command word','`which git` push'),
            ('wrapped command-word substitution','command $(which git) push'),
        ]:
            if fast and label!='command-word substitution': continue
            # Hidden command words ask without executing the generated input.
            case(label,cmd,args=['origin','wipetracked'],branch='wipetracked',want='ask',text='not judged')
        for label,cmd in [
            ('backtick push body','`git push origin wip:main`'),
            ('continuation after git','git '+chr(92)+chr(10)+'  push origin wip:main'),
            ('continuation after push','git push '+chr(92)+chr(10)+'  origin wip:main'),
            ('continuation before option','git push origin wip:main '+chr(92)+chr(10)+'  --no-verify'),
            ('shell here-string','bash <<< "git push origin wip:main"'),
            ('printf shell input',"printf 'git push origin wip:main\\n' | sh"),
            ('printf format shell input',"printf '%s\\n' 'git push origin wip:main' | sh"),
            ('echo shell input',"echo 'git push origin wip:main' | bash"),
        ]:
            if fast and label not in ('continuation after git','printf shell input'): continue
            case(label,cmd,args=['origin','wip:main'],want='ask',text='not judged') if label=='backtick push body' else case(label,cmd,args=['origin','wip:main'])
        if not fast:
            case('cat here-string is data','cat <<< "git push origin wip:main"',want='silent')
            case('trap visible push',"trap 'git push' EXIT",args=['origin','wipetracked'],branch='wipetracked',want='ask',text='wrapper or shell construct')
            case('earlier exported Git directory','export GIT_DIR=$WORK/.git; git push origin wip:main',args=['origin','wip:main'],outside=True,want='ask',text='earlier export')
            case('xargs placeholders','xargs -I{} git push origin {} <<< "wip:main"',args=['origin','wip:main'],want='ask',text='wrapper or shell construct')
            case('variable command word','GIT=git; $GIT push origin wip:main',args=['origin','wip:main'],want='ask',text='not judged')
            case('braced variable command word','GIT=git; ${GIT} push origin wip:main',args=['origin','wip:main'],want='ask',text='not judged')
            case('known no-op merge','git merge main && git push',want='silent')
            for op in ('reset','rebase','cherry-pick','am','revert'):
                case('unknown prior '+op,'git '+op+' main && git push',want='silent' if op=='reset' else 'ask',text='' if op=='reset' else 'earlier git '+op)
            case('unknown commit amend','git commit --amend -m x && git push',prior=[['commit','--amend','-m','x']])
            case('unknown commit paths','git commit f01.txt -m x && git push',prior=[['commit','f01.txt','-m','x']])
            case('restore from another tree is unresolved','git restore --staged --source=wipetracked . && git commit -m wipe && git push',
                 prior=[['restore','--staged','--source=wipetracked','.'],['commit','-m','wipe']],want='ask',text='restore options')
            def conversions(w,b):
                staged(w,b); (w/'.gitattributes').write_text('*.txt text=auto\n')
            case('plain index commit needs no content conversion','git commit -m wipe && git push',prior=[['commit','-m','wipe']],setup=conversions)
            case('working-tree content conversion is unresolved','git commit -am wipe && git push',prior=[['commit','-am','wipe']],setup=conversions,
                 want='ask')
            def many_tracked(w,b):
                names=[f'bulk{i}.txt' for i in range(2000)]
                for name in names: (w/name).write_text('tracked\n')
                g(w,'add','--',*names); g(w,'commit','-qm','many tracked files')
            case('2000-file commit-a stays quiet within the push deadline','git commit -am x && git push',prior=[['commit','-am','x']],setup=many_tracked)

            def docs(w,b):
                (w/'docs').mkdir(); (w/'docs/keep.txt').write_text('keep\n')
                g(w,'add','docs/keep.txt'); g(w,'commit','-qm','tracked docs')
            def docs_removed(w,b): docs(w,b); removed(w,b)
            def docs_staged(w,b): docs(w,b); staged(w,b)
            names=[f'f{i:02}.txt' for i in range(1,41)]
            for label,commands,setup in [
                ('plain commit',[['commit','-m','wipe']],docs_staged),
                ('commit-a',[['commit','-am','wipe']],docs_removed),
                ('add-u',[['add','-u'],['commit','-m','wipe']],docs_removed),
                ('add-all',[['add','-A'],['commit','-m','wipe']],docs_removed),
                ('literal paths',[['add','--',*['../'+n for n in names]],['commit','-m','wipe']],docs_removed),
                ('git-rm',[['rm','--',*['../'+n for n in names]],['commit','-m','wipe']],docs),
                ('restore subfolder only',[['restore','--staged','.'],['commit','-m','wipe']],docs_staged),
            ]:
                cmd=' && '.join('git '+' '.join(c) for c in commands)+' && git push'
                prior=[['-C','docs',*c] for c in commands]
                case('C subfolder '+label,cmd,prior=prior,setup=setup,cwd='docs',cfg={'add_all':'off'})
            case('C cd then commit-a','cd docs && git commit -am wipe && git push',
                 prior=[['-C','docs','commit','-am','wipe']],setup=docs_removed)
            case('C subfolder add-dot does not stage root removals','git add . && git commit -m x && git push',
                 prior=[['-C','docs','add','.'],['-C','docs','commit','-m','x']],setup=docs_removed,cwd='docs',cfg={'add_all':'off'})
            def docs_modified(w,b): docs(w,b); (w/'docs/keep.txt').write_text('changed\n')
            case('C subfolder clean modification','git commit -am x && git push',
                 prior=[['-C','docs','commit','-am','x']],setup=docs_modified,cwd='docs')
            case('C subfolder git-mv','git mv keep.txt renamed.txt && git commit -m mv && git push',
                 prior=[['-C','docs','mv','keep.txt','renamed.txt'],['-C','docs','commit','-m','mv']],setup=docs,cwd='docs')
            for cwd,setup in [(None,removed),('docs',docs_removed)]:
                commands=[['stage','-u'],['commit','-m','wipe']]
                case('C stage-u '+(cwd or 'root'),'git stage -u && git commit -m wipe && git push',
                     prior=[(['-C',cwd] if cwd else [])+c for c in commands],setup=setup,cwd=cwd)
            case('C stage literal paths','git stage -- '+' '.join(names)+' && git commit -m wipe && git push',
                 prior=[['stage','--',*names],['commit','-m','wipe']],setup=removed)
            case('C stage clean','git stage f01.txt && git commit -m x && git push',
                 prior=[['stage','f01.txt'],['commit','-m','x']])

            reason='earlier deleting command'
            for label,head in [('rm glob','rm f*.txt'),('rm literal','rm '+' '.join(names)),
                               ('find delete',"find . -name 'f*.txt' -delete"),
                               ('xargs rm',"git ls-files 'f*.txt' | xargs rm")]:
                case('C '+label+' before commit-a',head+' && git commit -am wipe && git push',
                     prior=[['$remove',*names],['commit','-am','wipe']],want='ask',text=reason)
            def sub(w,b):
                (w/'sub').mkdir()
                for name in names: g(w,'mv',name,'sub/'+name)
                g(w,'commit','-qm','tracked subfolder')
            for option in ('-u','-A','.'):
                case('C rm directory before add '+option,'rm -rf sub && git add '+option+' && git commit -m wipe && git push',
                     prior=[['$remove','sub'],['add',option],['commit','-m','wipe']],setup=sub,
                     cfg={'add_all':'off'},want='ask',text=reason)
            case('C rm directory before literal staging','rm -rf sub && git add sub && git commit -m wipe && git push',
                 prior=[['$remove','sub'],['add','sub'],['commit','-m','wipe']],setup=sub,want='ask',text=reason)
            case('C subfolder rm root files then commit-a','rm ../f*.txt && git commit -am wipe && git push',
                 prior=[['$remove',*names],['-C','docs','commit','-am','wipe']],setup=docs,cwd='docs',want='ask',text=reason)
            def restored(w,b):
                data={n:(w/n).read_bytes() for n in names}; staged(w,b)
                for n,value in data.items(): (w/n).write_bytes(value)
            case('C clean before add-all','git clean -fd && git add -A && git commit -m wipe && git push',
                 prior=[['clean','-fd'],['add','-A'],['commit','-m','wipe']],setup=restored,
                 cfg={'add_all':'off'},want='ask',text=reason)
            def build_dirs(w,b):
                for name in ('build','dist'): (w/name).mkdir(); (w/name/'output.txt').write_text('untracked\n')
            case('C untracked build cleanup stays quiet','rm -rf build dist && git commit -am x && git push',
                 prior=[['$remove','build','dist'],['commit','-am','x']],setup=build_dirs)
            case('C rm before plain index commit stays quiet','rm f*.txt && git commit -m x && git push',
                 prior=[['$remove',*names],['commit','-m','x']])
            case('C rm after commit stays quiet','git commit -m x; rm f*.txt; git push',
                 prior=[['commit','-m','x'],['$remove',*names]])
            case('C arbitrary script removal is outside reader',"python3 -c 'import pathlib; [p.unlink() for p in pathlib.Path().glob(\"f*.txt\")]' && git commit -am x && git push",
                 prior=[['$remove',*names],['commit','-am','x']],want='silent')
            case('C plumbing removal is outside reader','git read-tree --empty && git commit -m x && git push',
                 prior=[['read-tree','--empty'],['commit','-m','x']],want='silent')

            for label,head,setup,extra in [
                ('xargs git-rm',"git ls-files 'f*.txt' | xargs git rm -q",None,[]),
                ('xargs zero git-rm',"git ls-files -z 'f*.txt' | xargs -0 git rm -q",None,[]),
                ('xargs cached git-rm','git ls-files sub | xargs git rm -q --cached',sub,['--cached']),
            ]:
                paths=['sub/'+n for n in names] if setup else names
                case('F '+label,head+' && git commit -m wipe && git push',
                     prior=[['rm','-q',*extra,'--',*paths],['commit','-m','wipe']],setup=setup,
                     want='ask',text='wrapper or shell construct')
            for wrapper in ('sudo','command','env','time','nohup','nice','timeout 30','caffeinate','exec'):
                case('F '+wrapper+' rm',wrapper+' rm -rf sub && git commit -am wipe && git push',
                     prior=[['$remove','sub'],['commit','-am','wipe']],setup=sub,want='ask',text=reason)
            for label,head in [
                ('absolute rm','/bin/rm -rf sub'),
                ('if rm','if [ -d sub ]; then rm -rf sub; fi'),
                ('for rm','for d in sub; do rm -rf "$d"; done'),
                ('for unlink','for f in sub/*; do unlink "$f"; done'),
                ('brace body','{ rm -rf sub; }'),
                ('find exec plus',"find sub -name '*.txt' -exec rm {} +"),
                ('find exec semicolon','find sub -type f -exec rm -f {} '+chr(92)+';'),
            ]:
                case('F '+label,head+'; git commit -am wipe && git push',
                     prior=[['$remove','sub'],['commit','-am','wipe']],setup=sub,want='ask',text=reason)
            for command in ('branch -vv','branch -v','branch -avv','branch --list','branch -r','status','log -1','diff','show --stat','remote -v'):
                case('F readonly '+command,'git '+command+' && git push',
                     prior=[command.split()])
            def modified(w,b): (w/'f01.txt').write_text('modified\n')
            for staging in ('add','stage'):
                case('F linked clean '+staging,'git '+staging+' f01.txt && git commit -m x && git push',
                     prior=[[staging,'f01.txt'],['commit','-m','x']],setup=modified)
            case('F xargs data is not a deleting command','xargs printf rm && git commit -am x && git push',
                 prior=[['commit','-am','x']])
            case('F wrapped untracked build cleanup','command rm -rf build dist && git commit -am x && git push',
                 prior=[['$remove','build','dist'],['commit','-am','x']],setup=build_dirs)

    print(f"{'✘' if failed else '✔'} line push selftest: {len(rows)-failed}/{len(rows)} passed; {failed} wrong; {time.monotonic()-started:.2f} seconds; local remotes only")
    if output: pathlib.Path(output).write_text(json.dumps(rows,indent=2)+'\n')
    return failed,rows


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument("--selftest", action="store_true"); p.add_argument('--hook'); p.add_argument('--old'); p.add_argument('--out'); p.add_argument('--fast',action='store_true'); p.add_argument('--closing',action='store_true'); p.add_argument('--linked',action='store_true'); p.add_argument('--final',action='store_true')
    a=p.parse_args(); failed,_=run(a.hook,a.old,a.out,a.fast,a.closing,a.linked,a.final); sys.exit(2 if failed else 0)
