"""Manual commands on the existing WebUI backend. No new dashboard."""
import argparse,json,urllib.request,urllib.error
p=argparse.ArgumentParser()
p.add_argument('action',choices=['status','trigger','oled','servo1','servo2','cycle','scan','config'])
p.add_argument('--url',default='http://127.0.0.1:7000')
p.add_argument('--values',help='JSON for config, e.g. {"event_confidence":0.55}')
a=p.parse_args()
path='status' if a.action=='status' else 'config' if a.action=='config' else 'test'
payload=None if a.action=='status' else json.loads(a.values) if a.action=='config' and a.values else {'action':a.action}
request=urllib.request.Request(a.url+'/api/peripherals/'+path,
    data=None if payload is None else json.dumps(payload).encode(),
    headers={'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(request,timeout=5) as response:print(json.dumps(json.load(response),indent=2))
except urllib.error.HTTPError as exc:
    raise SystemExit(f'HTTP {exc.code}: {exc.read().decode()}')
