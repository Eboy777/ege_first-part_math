"""Fixed Aijuju endpoint; credentials and raw failures never enter logs."""
import json
import os
import subprocess
import tempfile
from django.conf import settings
from prompts.promptkit import parse_response,validate_response

class AIUnavailable(Exception):pass

def complete(role,context,messages):
    key=os.environ.get('AIJUJU_API_KEY','')
    if not key:
        try:key=(settings.STATE_DIR/'aijuju.key').read_text().strip()
        except OSError:raise AIUnavailable from None
    if not key:raise AIUnavailable
    payload={'model':'gpt-6.1-sol','messages':messages,'max_tokens':1800,'response_format':{'type':'json_object'}}
    name=None
    try:
        fd,name=tempfile.mkstemp(prefix='ai-auth-',dir=settings.STATE_DIR)
        with os.fdopen(fd,'w') as f:f.write('Authorization: Bearer '+key)
        # No redirects; TLS verification stays enabled. Key is not a process argument.
        proc=subprocess.run(['/usr/bin/curl','--silent','--show-error','--max-time','55','--max-filesize','2000000','--header','@'+name,'--header','Content-Type: application/json','--data-binary','@-','--write-out','\n%{http_code}','https://api.aijuju.rest/v1/chat/completions'],input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,timeout=60)
        if proc.returncode:raise AIUnavailable
        raw,status=proc.stdout.rsplit('\n',1)
        if status!='200':raise AIUnavailable
        body=json.loads(raw);choice=body['choices'][0]
        if choice.get('finish_reason')!='stop':raise AIUnavailable
        value=parse_response(choice['message']['content']);validate_response(value,role,context)
        return value
    except Exception:raise AIUnavailable from None
    finally:
        if name:
            try:os.unlink(name)
            except OSError:pass
