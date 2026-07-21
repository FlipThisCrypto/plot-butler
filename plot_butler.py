#!/usr/bin/env python3
"""The Plot Butler dashboard and plot transfer scheduler.

Plot rsyncs share the Tailscale path with chia_recompute_server (port 11989)
to chiamain. Farming recompute is latency-sensitive (~28s signage window);
bulk plot copies are not. This process therefore throttles transfers and
pauses new ones when recompute latency climbs into stale-share territory.
"""
import glob,json,os,re,shlex,signal,subprocess,threading,time
from datetime import datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STAGING=Path('/home/smokey/plots/staging')
SPOOL=Path('/media/smokey/1002/plot-butler/staging')
REMOTE='chiamain@100.101.40.76'
MIN_FREE_GB=90
PORT=int(os.environ.get('PLOT_BUTLER_PORT','8088'))

# Shared path with recompute: one bulk stream, modest ceiling, adaptive pause.
MAX_ACTIVE_TRANSFERS=1
RSYNC_BWLIMIT_KBPS=12000          # 12 MiB/s — leaves headroom for recompute RTT
RECOMPUTE_WINDOW_S=300           # journal sample window for latency stats (5 min)
RECOMPUTE_PAUSE_P90_MS=5000      # pause new transfers when recent p90 exceeds this
RECOMPUTE_RESUME_P90_MS=2500     # resume only after p90 cools below this
RECOMPUTE_CRITICAL_MAX_MS=20000  # also pause if any recent sample is this slow
TRANSFER_POLL_S=3                # remote size poll interval (less SSH chatter)
STAGING_SETTLE_S=60

lock=threading.RLock()
active={}
cache={'at':0,'drives':[],'temps':[],'plots':set()}
state={
 'name':'The Plot Butler','updated':0,'plot':{},'gpus':[],'recompute':{},
 'drives':[],'temperatures':[],'network':[],'transfers':[],
 'history':{'gpu':[],'transfers':[],'recompute_p90':[]},'alerts':[],
 'transfer_policy':{},
}
# hysteresis for transfer gate
_xfer_paused=False

def run(a,t=8):
 try:return subprocess.run(a,text=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=t).stdout.strip()
 except Exception:return ''

def ssh(c,t=10):
 return run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=4',REMOTE,c],t)

def gpus():
 out=[]; raw=run(['nvidia-smi','--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.total,memory.used,power.draw,power.limit','--format=csv,noheader,nounits'])
 for l in raw.splitlines():
  p=[x.strip() for x in l.split(',')]
  if len(p)>=8:
   try:out.append({'index':int(p[0]),'name':p[1],'temp_f':round(float(p[2])*9/5+32,1),'util':float(p[3]),'mem_total':float(p[4]),'mem_used':float(p[5]),'power':float(p[6]),'power_limit':float(p[7])})
   except ValueError:pass
 return out

def local_drives():
 out=[]
 for l in run(['df','-P','-T']).splitlines()[1:]:
  p=l.split()
  if len(p)>=7 and (p[0].startswith('/dev/') or p[6]=='/'):
   try:out.append({'scope':'local','device':p[0],'mount':p[6],'fs':p[1],'size_gb':round(int(p[2])/1048576,1),'used_gb':round(int(p[3])/1048576,1),'free_gb':round(int(p[4])/1048576,1),'used_pct':int(p[5].rstrip('%'))})
   except ValueError:pass
 return out

def remote_drives():
 by={}; script='''for p in /media/chiamain/*; do [ -d "$p" ] || continue; df -P -T "$p" | tail -1 | awk -v p="$p" '{print "DF|"p"|"$1"|"$2"|"$3"|"$4"|"$5"|"$6}'; done'''
 for l in ssh(script,20).splitlines():
  p=l.split('|')
  if len(p)>=8 and p[0]=='DF':
   try:
    r={'scope':'remote','mount':p[1],'device':p[2],'fs':p[3],'size_gb':round(int(p[4])/1048576,1),'used_gb':round(int(p[5])/1048576,1),'free_gb':round(int(p[6])/1048576,1),'used_pct':int(p[7].rstrip('%'))}
    if r['device']!='/dev/sda2' and r['fs']!='vfat':by[p[1]]=r
   except ValueError:pass
 eligible=[x for x in by if by[x]['free_gb']>MIN_FREE_GB]
 if eligible:
  paths=' '.join(shlex.quote(x) for x in eligible); cmd=f'''for p in {paths}; do dev=$(findmnt -n -o SOURCE --target "$p"); disk=$(lsblk -no PKNAME "$dev" 2>/dev/null); [ -z "$disk" ] && disk=$(basename "$dev"); model=$(lsblk -dn -o MODEL /dev/$disk 2>/dev/null | xargs); temp=$(sudo -n smartctl -A /dev/$disk 2>/dev/null | awk '/Temperature_Celsius|Airflow_Temperature_Cel/{{print $10; exit}}'); health=$(sudo -n smartctl -H /dev/$disk 2>/dev/null | awk -F: '/SMART overall-health|SMART Health Status/{{gsub(/^[ \\t]+/,"",$2); print $2; exit}}'); echo "DISK|$p|/dev/$disk|$model|$temp|$health"; done'''
  for l in ssh(cmd,20).splitlines():
   p=l.split('|')
   if len(p)>=6 and p[0]=='DISK' and p[1] in by:by[p[1]].update({'disk':p[2],'model':p[3],'temp_c':p[4] or None,'health':p[5] or 'unknown'})
 return list(by.values())

def temps():
 out=[]
 for label,c in re.findall(r'^([^:\n]+):\s+\+?(-?\d+(?:\.\d+)?)°C',run(['sensors'],5),re.M):
  low=label.lower(); kind='CPU' if any(x in low for x in ('core','package','tctl','tdie','cpu','ccd')) else ('HBA/controller' if any(x in low for x in ('hba','sas','raid','adapter')) else 'system'); out.append({'label':label.strip(),'kind':kind,'source':'lm-sensors','temp_f':round(float(c)*9/5+32,1)})
 for f in glob.glob('/sys/class/nvme/nvme*/hwmon*/temp*_input'):
  try:out.append({'label':'local NVMe /dev/'+Path(f).parts[4]+' '+Path(f).stem,'kind':'NVMe','source':'kernel hwmon','temp_f':round(float(Path(f).read_text())/1000*9/5+32,1)})
  except (ValueError,IndexError,OSError):pass
 return out

def remote_temps(ds):
 out=[]
 for label,c in re.findall(r'^([^:\n]+):\s+\+?(-?\d+(?:\.\d+)?)°C',ssh('sensors 2>/dev/null',8),re.M):
  out.append({'label':'chiamain · '+label.strip(),'kind':'CPU' if any(x in label.lower() for x in ('core','package','cpu','ccd')) else 'system','source':'lm-sensors','temp_f':round(float(c)*9/5+32,1)})
 for d in ds:
  if d.get('temp_c') not in (None,''):
   out.append({'label':'chiamain · '+d['mount'],'kind':'HDD','source':'smartctl','temp_f':round(float(d['temp_c'])*9/5+32,1)})
 return out

def remote_plot_names():
 raw=ssh('for p in /media/chiamain/*; do [ -d "$p" ] || continue; find "$p" -maxdepth 1 -type f -name "plot-k32-c7-*.plot" -size +70G -printf "%f\\n" 2>/dev/null; done | sort -u',20)
 return {x[:-5] if x.endswith('.plot') else x for x in raw.splitlines() if x}

def history():
 files=[]; seen=set(); starts=[]; names=[]; totals=[]
 for f in glob.glob('/home/smokey/logs/gigahorse-c7-*.log'):
  r=os.path.realpath(f)
  if r in seen:continue
  seen.add(r); t=Path(r).read_text(errors='replace'); files.append(r)
  starts+=re.findall(r'Crafting plot .* \((\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)\)',t)
  names+=re.findall(r'Plot Name: (plot-k32-c7-\S+)',t)
  totals+=[float(x) for x in re.findall(r'Total plot creation time was ([0-9.]+) sec',t)]
 un=[]
 for n in names:
  if n not in un:un.append(n)
 entries=[]
 for i,d in enumerate(totals):
  s=starts[i] if i<len(starts) else None
  try:e=time.mktime(datetime.strptime(s,'%Y/%m/%d %H:%M:%S').timetuple()) if s else 0
  except ValueError:e=0
  entries.append({'name':un[i] if i<len(un) else None,'start_epoch':e,'start_text':s,'duration_s':d,'complete_epoch':e+d if e else 0})
 s=starts[-1] if starts else None
 try:ep=time.mktime(datetime.strptime(s,'%Y/%m/%d %H:%M:%S').timetuple()) if s else 0
 except ValueError:ep=0
 return entries,un,s,ep

def plot_status():
 logs=sorted(glob.glob('/home/smokey/logs/gigahorse-c7-*.log'),key=os.path.getmtime)
 log=logs[-1] if logs else ''; text=Path(log).read_text(errors='replace')[-30000:] if log else ''
 h,names,last_start,last_ep=history(); totals=[x['duration_s'] for x in h]; now=time.time()
 starts=list(re.finditer(r'Crafting plot .* \((\d{4}/\d\d/\d\d \d\d:\d\d:\d\d)\)',text))
 done=list(re.finditer(r'Total plot creation time was ([0-9.]+) sec',text))
 sr=starts[-1] if starts else None; dr=done[-1] if done else None
 current=bool(sr and (not dr or sr.start()>dr.start()))
 phase='plotting' if current else ('complete' if dr else 'idle')
 ph=list(re.finditer(r'\[(P[1-4])\]',text))
 if current and ph:phase=ph[-1].group(1).lower()
 pid=run(['bash','-lc','ps -eo pid=,comm= | awk "$2==\\"cuda_plot_k32\\"{print \\$1; exit}"'])
 pid=int(pid.split()[0]) if pid.isdigit() else None
 compute=sum(totals); count=len(totals); avg=compute/count if count else 0
 first=time.mktime(datetime.strptime(h[0]['start_text'],'%Y/%m/%d %H:%M:%S').timetuple()) if h and h[0]['start_text'] else 0
 last=h[-1] if h else None
 today=datetime.now().astimezone().replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
 waits=list(re.finditer('Waiting for 88 GiB available space',text))
 waiting=bool(waits and (not sr or waits[-1].start()>sr.start()))
 active_rate=count/(compute/3600) if compute else 0
 wall_rate=count/((now-first)/3600) if first else 0
 files=list(STAGING.glob('*.plot*'))+list(SPOOL.glob('*.plot*'))
 return {
  'phase':phase,
  'progress_pct':{'p1':12,'p2':30,'p3':88,'p4':98,'complete':100,'plotting':5,'idle':0}.get(phase,5),
  'compression':'C7',
  'plot_name':re.findall(r'Plot Name: (\S+)',text)[-1] if re.findall(r'Plot Name: (\S+)',text) else None,
  'pid':pid,'tail':text.splitlines()[-10:],
  'elapsed_s':round((now-last_ep) if current else (float(dr.group(1)) if dr else 0),1),
  'compute_total_s':round(compute,1),'average_plot_s':round(avg,1) if avg else None,
  'completed_count':count,'created_count':count,'plot_names':names,
  'session_elapsed_s':round(now-first,1) if first else 0,
  'active_rate_plots_per_hour':round(active_rate,2) if active_rate else None,
  'wall_rate_plots_per_hour':round(wall_rate,2) if wall_rate else None,
  'plots_per_hour':round(active_rate,2) if active_rate else None,
  'actual_plots_today':sum(x['complete_epoch']>=today for x in h),
  'actual_plots_24h':sum(x['complete_epoch']>=now-86400 for x in h),
  'expected_plots_per_day':round(86400/avg,2) if avg else None,
  'last_started_at':datetime.fromtimestamp(last_ep).astimezone().isoformat() if last_ep else None,
  'last_completed_at':datetime.fromtimestamp(last['complete_epoch']).astimezone().isoformat() if last else None,
  'waiting_for_staging':waiting,
  'idle_s':round(now-last['complete_epoch'],1) if waiting and last else 0,
  'staging_files':[{'name':x.name,'bytes':x.stat().st_size,'tmp':x.name.endswith('.tmp')} for x in files],
 }

_RECOMP_LINE=re.compile(
 r'Request from \S+ for K\d+ C\d+ took ([0-9.]+) ms \(used_gpu = (\d+), is_fail = (\d+)\)'
)

def recompute_stats(window_s=RECOMPUTE_WINDOW_S):
 """Parse chia-recompute.service journal for recent request latencies."""
 lines=run(
  ['journalctl','-u','chia-recompute.service',f'--since={int(window_s)} seconds ago','--no-pager','-o','cat'],
  8,
 ).splitlines()
 times=[]; fails=0; gpu_hits=0
 for l in lines:
  m=_RECOMP_LINE.search(l)
  if not m:continue
  try:ms=float(m.group(1))
  except ValueError:continue
  times.append(ms)
  if m.group(3)=='1':fails+=1
  if m.group(2)=='1':gpu_hits+=1
 times.sort()
 n=len(times)
 def pct(p):
  if not n:return None
  return round(times[min(n-1,max(0,int(p/100*(n-1))))],2)
 service=run(['systemctl','is-active','chia-recompute.service'],3) or 'unknown'
 avg=round(sum(times)/n,2) if n else None
 p90=pct(90); p99=pct(99); mx=round(times[-1],2) if n else None
 # health for farming: responses well under the ~28s SP window
 if not n:
  health='idle' if service=='active' else 'down'
 elif (mx or 0)>=RECOMPUTE_CRITICAL_MAX_MS or (p90 or 0)>=15000:
  health='critical'
 elif (p90 or 0)>=RECOMPUTE_PAUSE_P90_MS or (mx or 0)>=10000:
  health='degraded'
 else:
  health='healthy'
 return {
  'service':service,'port':11989,'window_s':window_s,
  'requests_recent':n,'fails_recent':fails,'gpu_hits':gpu_hits,
  'latency_ms':{
   'min':round(times[0],2) if n else None,
   'p50':pct(50),'p90':p90,'p99':p99,'max':mx,'avg':avg,
  },
  'health':health,
  'over_5s':sum(1 for x in times if x>5000),
  'over_15s':sum(1 for x in times if x>15000),
  'over_25s':sum(1 for x in times if x>25000),
 }

def transfer_allowed(rc):
 """Hysteresis gate: farming latency wins over plot shipping."""
 global _xfer_paused
 lat=rc.get('latency_ms') or {}
 p90=lat.get('p90'); mx=lat.get('max')
 n=rc.get('requests_recent') or 0
 reason='ok'
 if rc.get('service')!='active':
  # recompute down is worse than slow transfers; still allow shipping but flag
  reason='recompute_inactive'
  _xfer_paused=False
 elif n==0 or p90 is None or mx is None:
  # No recent proofs: do not hold the gate forever on a stale pause.
  if _xfer_paused:
   _xfer_paused=False
   reason='resumed no-recent-recompute'
  else:
   reason='ok idle-recompute'
 elif not _xfer_paused:
  if p90>=RECOMPUTE_PAUSE_P90_MS or mx>=RECOMPUTE_CRITICAL_MAX_MS:
   _xfer_paused=True
   reason=f'pause p90={p90}ms max={mx}ms'
  else:
   reason='ok'
 else:
  if p90<=RECOMPUTE_RESUME_P90_MS and mx<RECOMPUTE_CRITICAL_MAX_MS:
   _xfer_paused=False
   reason='resumed cool-down'
  else:
   reason=f'held p90={p90}ms max={mx}ms'
 return (not _xfer_paused), reason, _xfer_paused

def send_plot(path,dest,bwlimit_kbps=RSYNC_BWLIMIT_KBPS):
 rec=active[path.name]
 expected=path.stat().st_size
 cmd=[
  'ionice','-c3','nice','-n','10',
  'rsync','-a','--whole-file','--inplace','--partial',
  f'--bwlimit={int(bwlimit_kbps)}','--info=progress2',
  str(path),f'{REMOTE}:{dest}/',
 ]
 p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
 with lock:
  rec.update({'pid':p.pid,'bwlimit_kbps':bwlimit_kbps,'status':'copying'})
 samples=[]
 while p.poll() is None:
  remote=ssh(
   f"find {shlex.quote(dest)} -maxdepth 1 -type f -name {shlex.quote(path.name)} -printf '%s\\n' 2>/dev/null | tail -1",
   5,
  )
  b=int(remote) if remote.isdigit() else rec.get('bytes',0)
  now=time.time(); prev=rec.get('bytes',b); pt=rec.get('sample_time',now)
  speed=max(0,(b-prev)/max(.1,now-pt))
  with lock:rec.update({'bytes':b,'speed':speed,'sample_time':now})
  samples.append(speed)
  time.sleep(TRANSFER_POLL_S)
 remote_size=ssh(f'stat -c %s {shlex.quote(dest+"/"+path.name)} 2>/dev/null || echo 0',8)
 ok=p.wait()==0 and remote_size.strip().splitlines()[-1:]==[str(expected)]
 if ok:
  path.unlink(missing_ok=True)
  ssh(f'chia plots add -d {shlex.quote(dest)}',8)
 with lock:
  rec.update({
   'done':time.time(),
   'status':'complete' if ok else 'failed',
   'average_speed':sum(samples)/len(samples) if samples else 0,
  })
  state['transfers'].append(dict(rec))
  active.pop(path.name,None)

def transfer_loop():
 while True:
  with lock:
   ds=list(state['drives'])
   rc=dict(state.get('recompute') or {})
   policy=dict(state.get('transfer_policy') or {})
  SPOOL.mkdir(parents=True,exist_ok=True)
  # Move finished plots off the NVMe one at a time. The HDD spool leaves NVMe
  # bandwidth for the active plotter.
  for f in STAGING.glob('*.plot'):
   if f.name in active or time.time()-f.stat().st_mtime<STAGING_SETTLE_S:continue
   target=SPOOL/(f.name+'.part'); final=SPOOL/f.name
   if target.exists() or final.exists():continue
   cp=subprocess.run(
    ['ionice','-c3','nice','-n','15','cp','--reflink=auto',str(f),str(target)],
    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
   )
   if cp.returncode==0 and target.stat().st_size==f.stat().st_size:
    target.rename(final); f.unlink(); break

  allowed=policy.get('allowed',True)
  if not allowed:
   time.sleep(10); continue

  choices=[d for d in ds if d.get('scope')=='remote' and d.get('free_gb',0)>MIN_FREE_GB]
  for f in list(SPOOL.glob('*.plot'))+list(STAGING.glob('*.plot')):
   if len(active)>=MAX_ACTIVE_TRANSFERS or f.name in active or not choices:continue
   if time.time()-f.stat().st_mtime<STAGING_SETTLE_S:continue
   used={x['dest'] for x in active.values()}
   avail=[d for d in choices if d['mount'] not in used]
   if not avail:continue
   dest=max(avail,key=lambda x:x.get('free_gb',0))['mount']
   with lock:
    active[f.name]={
     'name':f.name,'dest':dest,'start':time.time(),'bytes':0,
     'total':f.stat().st_size,'speed':0,'average_speed':0,'status':'copying',
     'bwlimit_kbps':RSYNC_BWLIMIT_KBPS,
    }
   threading.Thread(target=send_plot,args=(f,dest),daemon=True).start()
   break  # at most one new start per loop tick
  time.sleep(10)

def refresh():
 while True:
  now=time.time(); gs=gpus(); p=plot_status()
  refresh_remote=now-cache['at']>=30
  if refresh_remote:
   ds=remote_drives(); rt=remote_temps(ds); rp=remote_plot_names()
   with lock:cache.update({'at':now,'drives':ds,'temps':rt,'plots':rp})
  with lock:
   rd=list(cache['drives']); rt=list(cache['temps']); rp=set(cache['plots']); tr=list(active.values())
  p['transferred_count']=len(set(p.get('plot_names',[])) & rp)
  p['active_transfers']=len(tr)
  p['queued_files']=len(p.get('staging_files',[]))
  p['created_count']=p.get('completed_count',0)
  gpu_t=[{'label':'local · GPU '+str(x['index'])+' · '+x['name'],'kind':'GPU','source':'nvidia-smi','temp_f':x['temp_f']} for x in gs]
  rc=recompute_stats()
  rc['device']=1
  rc['gpu1_util']=next((x['util'] for x in gs if x['index']==1),0)
  allowed,reason,paused=transfer_allowed(rc)
  policy={
   'allowed':allowed,'paused':paused,'reason':reason,
   'max_active':MAX_ACTIVE_TRANSFERS,'bwlimit_kbps':RSYNC_BWLIMIT_KBPS,
   'pause_p90_ms':RECOMPUTE_PAUSE_P90_MS,'resume_p90_ms':RECOMPUTE_RESUME_P90_MS,
   'critical_max_ms':RECOMPUTE_CRITICAL_MAX_MS,
  }
  net=[]
  for l in open('/proc/net/dev').read().splitlines()[2:]:
   if ':' in l:
    i,v=l.split(':',1); a=v.split()
    if i.strip()!='lo' and len(a)>=9:
     net.append({'iface':i.strip(),'rx':int(a[0]),'tx':int(a[8])})
  alerts=[]
  if rc.get('health')=='critical':
   alerts.append({'level':'critical','msg':f"Recompute latency critical (p90={rc['latency_ms'].get('p90')}ms max={rc['latency_ms'].get('max')}ms); plot transfers paused"})
  elif rc.get('health')=='degraded':
   alerts.append({'level':'warn','msg':f"Recompute latency degraded (p90={rc['latency_ms'].get('p90')}ms); protecting farming path"})
  if paused:
   alerts.append({'level':'info','msg':f'Plot transfers gated: {reason}'})
  with lock:
   state.update({
    'updated':now,'plot':p,'gpus':gs,'drives':local_drives()+rd,
    'temperatures':temps()+gpu_t+rt,'network':net,'recompute':rc,
    'transfer_policy':policy,'alerts':alerts,
   })
   state['transfers']=state['transfers'][-100:]
   state['history']['gpu']=(state['history']['gpu']+[
    {'t':now,'g0':next((x['util'] for x in gs if x['index']==0),0),
     'g1':next((x['util'] for x in gs if x['index']==1),0)}
   ])[-120:]
   speeds=[x.get('speed',0) for x in active.values()]
   state['history']['transfers']=(state['history']['transfers']+[{'t':now,'speed':sum(speeds)}])[-120:]
   p90=rc.get('latency_ms',{}).get('p90') or 0
   state['history']['recompute_p90']=(state['history']['recompute_p90']+[{'t':now,'p90':p90}])[-120:]
  time.sleep(5)

class Handler(BaseHTTPRequestHandler):
 def do_POST(self):
  svc={'/api/start-plotting':'gigahorse-plotter.service','/api/start-recompute':'chia-recompute.service'}.get(self.path)
  if not svc:self.send_error(404);return
  ok=run(['sudo','-n','systemctl','start',svc],12) is not None and run(['systemctl','is-active',svc],5)=='active'
  body=json.dumps({'ok':ok,'service':svc}).encode()
  self.send_response(200 if ok else 503); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(body)
 def do_GET(self):
  if self.path=='/api/state':
   with lock:
    d=dict(state); d['transfers']=state['transfers']+list(active.values())
   b=json.dumps(d).encode()
   self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b); return
  if self.path in ('/','/index.html'):
   b=(ROOT/'index.html').read_bytes()
   self.send_response(200); self.send_header('Content-Type','text/html'); self.end_headers(); self.wfile.write(b); return
  self.send_error(404)
 def log_message(self,*a):pass

if __name__=='__main__':
 STAGING.mkdir(parents=True,exist_ok=True)
 threading.Thread(target=refresh,daemon=True).start()
 threading.Thread(target=transfer_loop,daemon=True).start()
 print(f'The Plot Butler listening on 0.0.0.0:{PORT}',flush=True)
 print(
  f'Transfer policy: max_active={MAX_ACTIVE_TRANSFERS} bwlimit={RSYNC_BWLIMIT_KBPS}KB/s '
  f'pause_p90={RECOMPUTE_PAUSE_P90_MS}ms resume_p90={RECOMPUTE_RESUME_P90_MS}ms',
  flush=True,
 )
 ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
