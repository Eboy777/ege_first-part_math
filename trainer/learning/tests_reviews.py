import io,json,tempfile,base64
from datetime import datetime,timedelta,timezone as dtz
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase,override_settings,Client
from django.utils import timezone
from .tests_training import TrainingTests as Fixtures
from .models import TrainingRun,Review,Attempt,Progress,ChatMessage,StudentError,PushSubscription,BankTask,Candidate
from .training import act,current,available
from .reviews import schedule,next_review,due_reviews
from .chat_service import send
from .notifications import valid_endpoint,send_due_notifications,vapid

class ReviewTests(TestCase):
 @classmethod
 def setUpTestData(cls):Fixtures.setUpTestData.__func__(cls)
 def setUp(self):
  self.day0=datetime(2026,1,1,12,tzinfo=dtz.utc)
  with patch('django.utils.timezone.now',return_value=self.day0):
   act(self.u,self.t,'start')
   for i in range(5):
    run=TrainingRun.objects.get(user=self.u,task_type=self.t);a=current(run);act(self.u,self.t,'answer',a.pk,a.task.answer)
    if i<4:act(self.u,self.t,'next',a.pk)
  self.run=TrainingRun.objects.get(user=self.u,task_type=self.t)
 def at(self,days):return patch('django.utils.timezone.now',return_value=self.day0+timedelta(days=days))
 def start(self):act(self.u,self.t,'start_review');return current(self.run)
 def finish(self):
  a=current(self.run);act(self.u,self.t,'answer',a.pk,a.task.answer);act(self.u,self.t,'next',a.pk);a=current(self.run);act(self.u,self.t,'answer',a.pk,a.task.answer)
 def test_mastery_dates_and_no_early_start(self):
  seven,thirty,ninety=schedule(self.run);self.assertEqual(Review.objects.count(),3);self.assertEqual(seven.due_at,self.day0+timedelta(days=7));self.assertIsNone(thirty.due_at);self.assertEqual(ninety.due_at,self.day0+timedelta(days=90))
  with self.at(6):self.assertIn('не наступил',act(self.u,self.t,'start_review'));self.assertFalse(due_reviews(self.u));self.assertEqual(Attempt.objects.count(),5)
 def test_two_independent_and_thirty_from_actual_completion(self):
  with self.at(20):
   self.start();self.finish()
  r=Review.objects.get(interval=7);thirty=Review.objects.get(interval=30);self.assertEqual(r.completed,2);self.assertEqual(thirty.due_at,self.day0+timedelta(days=50))
  self.run.refresh_from_db();self.assertEqual(self.run.completed,5);self.assertEqual(self.run.mastered_at,self.day0);self.assertEqual(Progress.objects.get(user=self.u).completed,5);self.assertEqual(StudentError.objects.count(),0)
  self.assertEqual(len(set(self.run.attempts.values_list('task_id',flat=True))),7)
 def test_wrong_answer_stays_and_no_auto_chat(self):
  with self.at(7):
   a=self.start();count=ChatMessage.objects.count();act(self.u,self.t,'answer',a.pk,'999');a.refresh_from_db();self.assertEqual(current(self.run).pk,a.pk);self.assertFalse(a.assisted);self.assertEqual(ChatMessage.objects.count(),count)
   act(self.u,self.t,'answer',a.pk,a.task.answer);act(self.u,self.t,'answer',a.pk,a.task.answer)
  self.assertEqual(Review.objects.get(interval=7).completed,1)
 def test_theory_replacement_and_stale_answer(self):
  with self.at(8):
   a=self.start();act(self.u,self.t,'theory',a.pk);act(self.u,self.t,'answer',a.pk,a.task.answer);self.assertEqual(Review.objects.get(interval=7).completed,0)
   act(self.u,self.t,'next',a.pk);b=current(self.run);self.assertNotEqual(a.task_id,b.task_id);self.assertEqual(b.stage,4);self.assertIn('не текущая',act(self.u,self.t,'answer',a.pk,a.task.answer))
 def test_ai_marks_review_and_keeps_credit(self):
  from .ai_provider import AIUnavailable
  with self.at(8):
   a=self.start()
   with patch('learning.chat_service.complete',side_effect=AIUnavailable) as api:send(self.u,'Помоги разобраться с задачей',self.t.pk,str(a.pk))
   self.assertEqual(api.call_args.args[1]['training_mode'],'review');a.refresh_from_db();self.assertTrue(a.assisted);act(self.u,self.t,'answer',a.pk,a.task.answer);self.assertEqual(Review.objects.get(interval=7).completed,0)
 def test_queue_multiple_overdue_no_skipped_credits(self):
  with self.at(150):
   self.assertEqual(len(due_reviews(self.u)),1);self.assertEqual(due_reviews(self.u)[0].interval,7);self.start();self.finish();self.assertFalse(due_reviews(self.u))
  with self.at(180):
   self.assertEqual(due_reviews(self.u)[0].interval,30);self.start();self.finish();self.assertEqual(due_reviews(self.u)[0].interval,90)
   message=act(self.u,self.t,'start_review');self.assertIn('закончились',message);self.assertIsNone(Review.objects.get(interval=90).started_at)
 def test_isolation_reload_and_no_task_before_due(self):
  self.client.force_login(self.u);path='/exam/2026/types/right-triangle'
  with self.at(7):
   self.client.post(path,{'action':'start_review'});a=current(self.run);self.client.get(path);self.assertEqual(current(self.run).pk,a.pk)
   self.assertIn('не текущая',act(self.other,self.t,'answer',a.pk,a.task.answer));self.assertEqual(due_reviews(self.other),[])
 @override_settings(TRAINER_EXAM_VERSION="2026")
 def test_number_counter_counts_types_not_checkpoints(self):
  self.client.force_login(self.u)
  with self.at(200):
   self.assertContains(self.client.get('/'),'Типов к повторению: 1');r=self.client.get('/exam/2026/tasks/1?review=due');self.assertContains(r,self.t.title);self.assertNotContains(r,'Площадь треугольника')

 def test_all_three_reviews_complete_without_reset(self):
  for i in range(9,12):
   candidate=Candidate.objects.create(source_url=f'https://example.org/{i}',source_task_id=str(i),source='test',task_type=self.t,rights_status='approved',license_or_permission='test')
   BankTask.objects.create(id=f'test-{i}',candidate=candidate,task_type=self.t,statement=f'Вычисли {i}+2',answer=str(i+2),answer_verified=True,verification_notes='test',family_key=f'f{i}',status='published')
  for days in (7,37,90):
   with self.at(days):self.start();self.finish()
  self.assertEqual(Review.objects.filter(completed=2).count(),3)
  with self.at(300):self.assertFalse(due_reviews(self.u));self.assertIn('не наступил',act(self.u,self.t,'start_review'))
  self.run.refresh_from_db();self.assertEqual(self.run.completed,5)

class NotificationTests(TestCase):
 def setUp(self):
  from django.contrib.auth import get_user_model
  self.u=get_user_model().objects.create_user('push-learner');self.other=get_user_model().objects.create_user('push-other');self.client.force_login(self.u)
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.override=override_settings(STATE_DIR=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)
 def payload(self):
  from cryptography.hazmat.primitives.asymmetric import ec
  from cryptography.hazmat.primitives import serialization
  p=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
  enc=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
  return {'endpoint':'https://web.push.apple.com/example','keys':{'auth':enc(b'a'*16),'p256dh':enc(p)}}
 def test_config_key_private_and_persistent(self):
  first=self.client.get('/api/notifications/config').json()['public_key'];self.assertEqual(first,self.client.get('/api/notifications/config').json()['public_key']);self.assertEqual((Path(self.temp.name)/'vapid.pem').stat().st_mode&0o777,0o600)
  self.assertEqual(len(base64.urlsafe_b64decode(first+'=')),65)
 def test_subscription_owner_unsubscribe_and_csrf(self):
  data=self.payload();self.assertEqual(self.client.post('/api/notifications/subscription',data,content_type='application/json').status_code,200)
  c=Client();c.force_login(self.other);c.post('/api/notifications/subscription',{'endpoint':data['endpoint'],'unsubscribe':True},content_type='application/json');self.assertEqual(PushSubscription.objects.count(),1)
  self.client.post('/api/notifications/subscription',{'endpoint':data['endpoint'],'unsubscribe':True},content_type='application/json');self.assertEqual(PushSubscription.objects.count(),0)
  c=Client(enforce_csrf_checks=True);c.force_login(self.u);self.assertEqual(c.post('/api/notifications/subscription',data,content_type='application/json').status_code,403)
 def test_reject_arbitrary_targets_and_bad_keys(self):
  for url in ['http://web.push.apple.com/example','https://127.0.0.1/private','https://web.push.apple.com.evil.test/x','https://web.push.apple.com:444/x','https://user@web.push.apple.com/x']:self.assertFalse(valid_endpoint(url))
  data=self.payload();data['keys']['auth']='invalid';self.assertEqual(self.client.post('/api/notifications/subscription',data,content_type='application/json').status_code,400)
 def test_manifest_and_worker_public_no_private_cache(self):
  c=Client();self.assertEqual(c.get('/manifest.webmanifest').json()['display'],'standalone');r=c.get('/sw.js');self.assertEqual(r.status_code,200);content=b''.join(r.streaming_content).decode();self.assertIn("addEventListener('push'",content);self.assertNotIn("addEventListener('fetch'",content)
 def test_sender_once_per_checkpoint_and_expired_cleanup(self):
  from types import SimpleNamespace
  data=self.payload();sub=PushSubscription.objects.create(user=self.u,endpoint=data['endpoint'],keys=data['keys']);due=[SimpleNamespace(pk=17)]
  with patch('learning.notifications.due_reviews',return_value=due),patch('pywebpush.webpush') as push:
   self.assertEqual(send_due_notifications(),1);self.assertEqual(send_due_notifications(),0);self.assertEqual(push.call_count,1)
  with patch('learning.notifications.due_reviews',return_value=[SimpleNamespace(pk=18)]),patch('pywebpush.webpush') as push:
   self.assertEqual(send_due_notifications(),1)
  from pywebpush import WebPushException
  with patch('learning.notifications.due_reviews',return_value=[SimpleNamespace(pk=19)]),patch('pywebpush.webpush',side_effect=WebPushException('gone',response=SimpleNamespace(status_code=410))):self.assertEqual(send_due_notifications(),0)
  self.assertFalse(PushSubscription.objects.exists())
 def test_logout_removes_browser_subscription(self):
  data=self.payload();self.client.post('/api/notifications/subscription',data,content_type='application/json');self.client.post('/logout');self.assertFalse(PushSubscription.objects.exists())

 def test_real_push_encryption_with_mocked_http(self):
  from pywebpush import webpush
  from types import SimpleNamespace
  key,_=vapid()
  with patch('requests.post',return_value=SimpleNamespace(status_code=201,text='')) as http:
   webpush(self.payload(),data='Пора повторить',vapid_private_key=key,vapid_claims={'sub':'https://example.org'},timeout=10)
  self.assertEqual(http.call_args.args[0],self.payload()['endpoint'])
  self.assertIsInstance(http.call_args.kwargs['data'],bytes)
  self.assertIn('authorization',{k.lower():v for k,v in http.call_args.kwargs['headers'].items()})
