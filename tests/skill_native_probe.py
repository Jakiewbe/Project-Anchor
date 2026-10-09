"""Opt-in real discovery and model-trigger evaluation in isolated projects.

Default: discovery only, no model requests. --live: real Codex natural-language
turns using existing login; no auth copy, no global config writes, ephemeral.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.atomic_io import encode_json
from core.config import install, uninstall, codex_home
from core.memory import init_project, load, doc_change, task_change
from core.native import CodexClient


def fixture(project, initialized=True, task=True):
    project.mkdir(parents=True)
    subprocess.run(["git","init",str(project)],check=True,capture_output=True)
    (project / "main.py").write_text('print(2 + 3)\n',encoding="utf-8")
    (project / "notes.txt").write_text('hello\n',encoding="utf-8")
    if initialized:
        init_project(project,project.name)
        state,content,_=load(project)
        goal=content['GOAL.md'].replace('待用户确认：填写一句话目标。','交付一个可运行的 Python 演示脚本及使用说明。').replace('待确认：填写可验证的交付条件。','main.py 输出可以验证，说明文档可供用户独立运行。').replace('待确认。','用户确认：只涉及本项目演示文件，不增加外部服务。')
        doc_change(project,0,'GOAL.md',goal,'测试用户已确认的固定目标',approved=True)
        if task:
            task_change(project,1,'add',{'task_id':'T1','title':'验证演示输出','plan':'approved','acceptance_criteria':['main.py 实际输出 5']},'固定验收任务')
            task_change(project,2,'update',{'task_id':'T1','status':'doing'},'实际进入验收阶段')


def state_bytes(project):
    return {p.name:p.read_bytes() for p in (project / '.agent').glob('*') if p.is_file() and p.name not in {'.lock'}}


def discovery(folder,installed_user=False,shared_home=None):
    user=folder/'隔离用户'
    home=shared_home if installed_user else user/'.codex'
    parent=Path.home()/'.agents/skills' if installed_user else user/'.agents/skills'
    project=folder/'原生发现 项目'
    fixture(project)
    if not installed_user:
        install(home,parent)
    env=dict(os.environ,HOME=str(user),USERPROFILE=str(user),PYTHONUTF8='1')
    with CodexClient(home,project,env) as client:
        if not installed_user:
            # Windows Rust home discovery uses the OS home, not a spoofed
            # USERPROFILE. Explicit process-only roots keep this probe isolated.
            client.request('skills/extraRoots/set',{'extraRoots':[str(parent)]})
        result=client.request('skills/list',{'cwds':[str(project)],'forceReload':True})
        (folder/'skills-list.json').write_bytes(encode_json(result))
        current=[s for e in result['data'] for s in e['skills'] if s['name']=='project-anchor' and Path(s['path'])==parent/'project-anchor/SKILL.md']
        if len(current)!=1 or not current[0]['enabled']:
            raise RuntimeError('Codex did not discover user .agents Skill')
        hooks=client.request('hooks/list',{'cwds':[str(project)]})
        assert {h['eventName'] for e in hooks['data'] for h in e['hooks']}=={'sessionStart','preCompact'}
    (folder/'skills-list.json').write_bytes(encode_json(result))
    return {'discovery':'PASS','scope':current[0]['scope'],'user_skill_path':current[0]['path'],
            'default_user_directory_verified':installed_user,'extra_roots':not installed_user,'hooks_independent':'PASS'}


CASES=[
 ('explicit',True,True,'$project-anchor 查看当前项目进度。不要改动任务。','progress'),
 ('init',False,False,'帮我初始化项目管理，使用当前目录名作为项目名。','init'),
 ('plan',True,False,'根据我的项目目标制定任务草案，并保存到项目任务账本。','plan'),
 ('task',True,True,'把 T1 标记为完成。验收证据：我已经实际运行 main.py，输出确实是 5。','task'),
 ('memory',True,True,'记录我们刚才确定的技术路线：采用 Python 标准库，状态用 JSON 文件保存，不使用数据库。这是已确认决策。','memory'),
 ('progress',True,True,'现在项目进度如何？还有哪些任务？只查看，不修改。','progress'),
 ('handoff',True,True,'整理一下工作状态，保存工作断点，准备切换会话。','handoff'),
 ('retro',True,True,'总结这个项目的经验教训，生成项目复盘草案。','retro'),
 ('doctor',True,True,'检查全局规则和 Hook 是否正常。只诊断，不更改配置。','doctor'),
 ('explain',True,True,'解释 main.py 的代码为什么输出 5。','negative'),
 ('script',True,True,'把 main.py 改为输出 6，只改这一个脚本。','negative'),
 ('knowledge',True,True,'为什么天空是蓝色的？','negative'),
 ('file',True,True,'把 notes.txt 里的 hello 改为你好，只改这一个文件。','negative'),
 ('uninitialized',False,False,'解释 main.py 的输出，不要修改任何文件。','negative')]


def live_case(folder,case,home,installed_user=False):
    name,initialized,has_task,prompt,expect=case
    project=folder/('模型测试 '+name)
    fixture(project,initialized,has_task)
    isolated_home=folder/('运行配置 '+name)
    if not installed_user:
        install(isolated_home,project/'.agents/skills')
    # True evidence for the completion prompt, produced before the model turn.
    execution=subprocess.run([sys.executable,str(project/'main.py')],capture_output=True,text=True,check=True)
    assert execution.stdout.strip()=='5'
    before=state_bytes(project)
    env=dict(os.environ,CODEX_HOME=str(home),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    command=[shutil.which('codex'),'--no-daemon','exec','--ignore-user-config','--disable','hooks','--disable','multi_agent',
             '--ephemeral','--approve-for-me','--json','-C',str(project),'-']
    started=time.monotonic()
    result=subprocess.run(command,input=prompt,cwd=project,env=env,capture_output=True,encoding='utf-8',errors='replace',timeout=240)
    (folder/(name+'.jsonl')).write_text(result.stdout,encoding='utf-8')
    (folder/(name+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
    events=[json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith('{')]
    commands=[e.get('item',{}).get('command','') for e in events if e.get('item',{}).get('type')=='command_execution']
    used=any('project-anchor' in c and ('SKILL.md' in c or 'run.py' in c) for c in commands)
    completed=any(e.get('type')=='turn.completed' for e in events) and result.returncode==0
    behavior=False
    reason='当前 Codex 执行策略阻止工具调用' if 'rejected: blocked by policy' in result.stderr else ''
    try:
        if expect=='negative':
            behavior=not used
            if not initialized:
                behavior=behavior and not (project/'.agent').exists()
        elif expect=='init':
            behavior=load(project)[0]['name']==project.name
        elif expect=='task':
            behavior=load(project)[2]['tasks'][0]['status']=='done'
        elif expect=='plan':
            entries=load(project)[2]['tasks']
            behavior=bool(entries) and all(t['plan']=='draft' for t in entries)
        elif expect=='memory':
            load(project)
            behavior=(project/'.agent/DECISIONS.md').read_bytes()!=before['DECISIONS.md']
        elif expect=='progress':
            behavior=state_bytes(project)==before
        elif expect=='handoff':
            s,_,ledger=load(project)
            behavior=(project/'.agent/CURRENT.md').read_bytes()!=before['CURRENT.md'] and s['current_task_revision']==ledger['revision'] and bool(list((project/'.agent/runtime/snapshots').glob('*.json')))
        elif expect=='retro':
            behavior=(project/'.agent/RETRO.md').is_file()
        elif expect=='doctor':
            behavior=any('doctor' in c and 'run.py' in c for c in commands) and state_bytes(project)==before
    except Exception as exc:
        reason=str(exc)
    passed=completed and behavior and (used or expect=='negative')
    return {'case':name,'expect':expect,'status':'PASS' if passed else 'FAIL','completed':completed,
            'used_skill_observed':used,'behavior':behavior,'seconds':round(time.monotonic()-started,1),
            'reason':reason,'usage':next((e.get('usage') for e in events if e.get('type')=='turn.completed'),None)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--user-skill',action='store_true',help='临时安装到真实用户 Skill 目录并在测试后安全卸载；其他 Codex 配置仍在隔离目录')
    parser.add_argument('--case',choices=[c[0] for c in CASES])
    parser.add_argument('--exclude',choices=[c[0] for c in CASES])
    args=parser.parse_args()
    folder=ROOT/'.test-runtime'/('skill-native-'+uuid.uuid4().hex)
    folder.mkdir(parents=True)
    shared_home=folder/'实际Skill的隔离配置'
    installed=False
    try:
        if args.user_skill:
            install(shared_home)
            installed=True
        result={'folder':str(folder),'native':discovery(folder,installed,shared_home),'model_cases':[]}
        print(json.dumps(result['native'],ensure_ascii=False),flush=True)
        if args.live:
            for case in CASES:
                if args.case and case[0]!=args.case:
                    continue
                if args.exclude and case[0]==args.exclude:
                    continue
                print('RUN '+case[0],flush=True)
                try:
                    item=live_case(folder,case,codex_home(),installed)
                except (OSError,subprocess.TimeoutExpired,RuntimeError) as exc:
                    item={'case':case[0],'status':'FAIL','reason':str(exc)}
                result['model_cases'].append(item)
                (folder/'result.json').write_bytes(encode_json(result))
                print(json.dumps(item,ensure_ascii=False),flush=True)
        result['automatic_trigger_guarantee']=False
        (folder/'result.json').write_bytes(encode_json(result))
    finally:
        if installed:
            uninstall(shared_home)
    print('RESULT '+str(folder/'result.json'),flush=True)
    return 1 if any(c['status']=='FAIL' for c in result['model_cases']) else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
