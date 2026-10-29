import hashlib,json,os,queue,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.memory import init_project,load,task_change,focus_change,doc_change
from core.clients import install_client
from core.native import CodexClient
OUT=ROOT/".agent/runtime/implementation151/native";OUT.mkdir(parents=True,exist_ok=True)
PROJECT=Path(tempfile.mkdtemp(prefix="Anchor151 原生接续 ")).resolve()
(PROJECT/'README.md').write_text('Read-only synthetic validation.\n',encoding='utf8')
init_project(PROJECT,'1.5 原生接续')
def change(action,payload):return task_change(PROJECT,load(PROJECT)[0]['revision'],action,payload,'用户授权的隔离验收',source='user')
for tid in ('OLD_HISTORY','CURRENT151'):
 change('add',{'task_id':tid,'title':tid,'deliverables':['README.md'],'acceptance_criteria':['仅核对状态'],'checks':[{'criterion':1,'kind':'review','inputs':['README.md']}]})
focus_change(PROJECT,load(PROJECT)[0]['revision'],['CURRENT151'],'明确本轮只读任务')
s,c,_=load(PROJECT);doc_change(PROJECT,s['revision'],'CURRENT.md',c['CURRENT.md']+'\n接续标记 NATIVE-151-FIRST。本轮仅只读核对，不执行任务。最终图面未验收。\n','合成断点',task_ids=['CURRENT151'])
install_client('agents',PROJECT/'.agent/runtime/installation',PROJECT/'.agents/skills')
SKILL=PROJECT/'.agents/skills/project-anchor/SKILL.md'
def fp(folder):
 return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file() and '.lock' not in p.name}
config=Path.home()/'.codex/config.toml';before_config=hashlib.sha256(config.read_bytes()).hexdigest()
results=[]
def wait(client,predicate,seconds=180):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  try:value=client.queue.get(timeout=.5)
  except queue.Empty:
   if client.process.poll() is not None:raise RuntimeError('app-server exited')
   continue
  client.events.append(value)
  (OUT/'native-events.json').write_text(json.dumps(client.events,ensure_ascii=False,indent=2),encoding='utf8')
  if value.get('method')=='error':raise RuntimeError(str(value.get('params',{}).get('error',{})))
  if predicate(value):return value
 raise RuntimeError('native validation timeout')
def turn(client,tid):
 prompt=f'这是用户授权的隔离只读验收。唯一目标项目是 {PROJECT}，使用该项目Skill {SKILL}，只读查询本轮范围与CURRENT。返回真实本轮任务ID、状态、断点标记、current_alignment及deliverable_coverage。明确最终图面未验收；不修改任何文件，不执行业务，不接续历史未完成项。'
 start=len(client.events);r=client.request('turn/start',{'threadId':tid,'input':[{'type':'text','text':prompt}]})
 turnid=r['turn']['id'];v=wait(client,lambda v:v.get('method')=='turn/completed' and v.get('params',{}).get('turn',{}).get('id')==turnid)
 if v['params']['turn']['status']!='completed':raise RuntimeError('model turn failed')
 events=client.events[start:];answer='\n'.join(str(e.get('params',{}).get('item',{}).get('text','')) for e in events if e.get('method')=='item/completed')
 commands=[e.get('params',{}).get('item',{}).get('command','') for e in events if e.get('method')=='item/started' and e.get('params',{}).get('item',{}).get('type')=='commandExecution']
 return answer,commands
try:
 with CodexClient(Path.home()/'.codex',PROJECT) as client:
  result=client.request('thread/start',{'cwd':str(PROJECT),'ephemeral':True,'approvalPolicy':'never','sandbox':'workspace-write','config':{'features.hooks':False,'features.multi_agent':False}})
  tid=result['thread']['id'];before=fp(PROJECT)
  answer,commands=turn(client,tid)
  passed='CURRENT151' in answer and 'NATIVE-151-FIRST' in answer and 'aligned' in answer and 'undeclared' in answer and '未验收' in answer and any('--focus' in c for c in commands) and fp(PROJECT)==before
  results.append({'case':'new-session-focus','pass':passed,'commands':commands,'answer':answer})
  if not passed:raise RuntimeError('fresh session did not meet acceptance')
  s,c,_=load(PROJECT);doc_change(PROJECT,s['revision'],'CURRENT.md',c['CURRENT.md'].replace('NATIVE-151-FIRST','NATIVE-151-LATEST'),'合成新断点',task_ids=['CURRENT151'])
  before=fp(PROJECT);client.request('thread/compact/start',{'threadId':tid})
  wait(client,lambda v:v.get('method')=='item/completed' and v.get('params',{}).get('item',{}).get('type')=='contextCompaction')
  answer,commands=turn(client,tid)
  passed='CURRENT151' in answer and 'NATIVE-151-LATEST' in answer and 'aligned' in answer and 'undeclared' in answer and '未验收' in answer and any('--focus' in c for c in commands) and fp(PROJECT)==before
  results.append({'case':'after-native-compaction','pass':passed,'commands':commands,'answer':answer})
except Exception as exc:results.append({'case':'native-blocker','pass':False,'error':str(exc)[:1200]})
unchanged=hashlib.sha256(config.read_bytes()).hexdigest()==before_config
summary={'passed':sum(x['pass'] for x in results),'failed':sum(not x['pass'] for x in results),'config_unchanged':unchanged,'hooks_disabled':True,'project':str(PROJECT),'results':results}
(OUT/'native-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(summary,ensure_ascii=False),flush=True)

raise SystemExit(0 if summary["failed"]==0 and unchanged else 1)
