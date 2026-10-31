"""Local deployment transport. Credentials stay out of argv and logs."""
import ipaddress
import re
from pathlib import Path
import pexpect

ROOT=Path(__file__).resolve().parent.parent

def config():
    values={}
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip('\"\'')
    ipaddress.ip_address(values['IP'])
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+',values['LOGIN']):raise ValueError('Invalid SSH login')
    domain=values['DOMEN'].removeprefix('https://').removeprefix('http://').rstrip('/').encode('idna').decode()
    if not re.fullmatch(r'[a-zA-Z0-9.-]+',domain):raise ValueError('Invalid domain')
    values['domain']=domain
    return values

def invoke(binary,args,timeout=180):
    cfg=config();child=pexpect.spawn(binary,args,encoding='utf-8',timeout=timeout,echo=False)
    output=[]
    while True:
        index=child.expect([r'(?i)password:',pexpect.EOF,pexpect.TIMEOUT])
        output.append(child.before)
        if index==0:child.sendline(cfg['PASSWORD'])
        elif index==1:break
        else:child.close(force=True);raise RuntimeError('SSH operation timed out')
    child.close()
    text=''.join(output)
    if child.exitstatus!=0:raise RuntimeError(f'Remote operation failed ({child.exitstatus}): '+text[-2500:])
    return text

def options():return ['-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(ROOT/'.runtime/deploy_known_hosts'),'-o','ConnectTimeout=15']
def run(command,timeout=180):
    cfg=config();return invoke('/usr/bin/ssh',options()+[cfg['LOGIN']+'@'+cfg['IP'],command],timeout)
def upload(local,remote):
    cfg=config();return invoke('/usr/bin/scp',options()+[str(local),cfg['LOGIN']+'@'+cfg['IP']+':'+remote])

if __name__=='__main__':
    import sys
    if sys.argv[1]=='run':print(run(sys.argv[2]))
    elif sys.argv[1]=='upload':print(upload(sys.argv[2],sys.argv[3]))
