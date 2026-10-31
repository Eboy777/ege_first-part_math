"""Internal read-only smoke checks using a temporary session, no password export."""
import json,uuid,secrets
from django.test import Client
from django.contrib.auth import get_user_model
from django.conf import settings
from learning.models import TrainingRun,StudentError
checks=[]
def check(name,value):checks.append({'check':name,'passed':bool(value)});print(name,bool(value))
host=settings.ALLOWED_HOSTS[0]
user=get_user_model().objects.get(username='student_b')
c=Client();c.force_login(user)
try:
    r=c.get('/',secure=True,HTTP_HOST=host);check('Imported catalog and progress',r.status_code==200 and '3 / 7 типов освоено' in r.content.decode())
    r=c.get('/api/mistakes',secure=True,HTTP_HOST=host);check('Imported mistakes',r.status_code==200 and len(r.json()['options'])==5)
    r=c.get('/exam/ege_profile_2026/types/ege26-1-3',secure=True,HTTP_HOST=host);check('Saved review',r.status_code==200 and 'Повторение · 30 дней' in r.content.decode())
    check('Existing errors preserved',StudentError.objects.filter(user=user).count()>=6)
    check('Three mastered types preserved',TrainingRun.objects.filter(user=user,completed=5).count()==3)
    check('Secure cookie flags',settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE and not settings.DEBUG)
finally:c.logout()
qa=get_user_model().objects.create_user('qa_deploy_'+uuid.uuid4().hex[:8],password=secrets.token_urlsafe(24))
try:
    # A synthetic password is generated and used only inside this server process.
    password=secrets.token_urlsafe(24);qa.set_password(password);qa.save()
    c=Client(enforce_csrf_checks=True);r=c.get('/login',secure=True,HTTP_HOST=host)
    from django.middleware.csrf import get_token
    token=c.cookies['csrftoken'].value
    r=c.post('/login',{'username':qa.username,'password':password,'csrfmiddlewaretoken':token},secure=True,HTTP_HOST=host,HTTP_REFERER='https://'+host+'/login')
    check('Login and CSRF with synthetic account',r.status_code==302)
    r=c.post('/api/mistakes/send',data=json.dumps({'operation':'answer','text':'5'}),content_type='application/json',secure=True,HTTP_HOST=host)
    check('CSRF rejection',r.status_code==403)
    c.logout()
finally:qa.delete()
print('ALL_CHECKS_PASSED',all(x['passed'] for x in checks))
if not all(x['passed'] for x in checks):raise SystemExit(1)
