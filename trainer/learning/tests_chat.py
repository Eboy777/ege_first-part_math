import io,json,tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.contrib.auth import get_user_model
from learning.tests_training import TrainingTests
from .models import Conversation,ChatMessage,ChatPhoto,StudentError,TrainingRun
from .chat_service import send,conversation,ChatConflict
from .ai_provider import AIUnavailable
from .training import act,current

REPLY={'message':'Какую формулу выберешь?','action':'reply','diagnosis':None,'exercise':None,'assessment':None}
class ChatTests(TestCase):
 @classmethod
 def setUpTestData(cls):TrainingTests.setUpTestData.__func__(cls)
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.override=override_settings(STATE_DIR=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)
 def active(self):
  act(self.u,self.t,'start');return current(TrainingRun.objects.get(user=self.u,task_type=self.t))
 def test_main_window_and_no_profile(self):
  c=conversation(self.u)
  for i in range(18):ChatMessage.objects.create(conversation=c,role='user',text=f'old{i}')
  with patch('learning.chat_service.complete',return_value=REPLY) as api:
   send(self.u,'Объясни дроби')
  role,context,messages=api.call_args.args
  self.assertEqual(role,'free_chat');self.assertIsNone(context['active_task_id'])
  self.assertEqual(sum(m['role']!='system' for m in messages),10)
  self.assertNotIn('old0',str(messages));self.assertNotIn('error_catalog',context)
  self.assertNotIn('student_errors',str(messages))
 def test_diagnosis_requires_real_wrong_submission_and_explanation(self):
  a=self.active();act(self.u,self.t,'answer',a.pk,'999')
  value={**REPLY,'action':'diagnosis_candidate','diagnosis':{'error_key':'pythagoras:sum_lengths','description':'Сложение катетов','evidence':'Я сложил длины катетов'}}
  with patch('learning.chat_service.complete',return_value=value),self.captureOnCommitCallbacks(execute=True):
   send(self.u,'Я сложил длины катетов и получил 14',self.t.pk,str(a.pk))
  self.assertEqual(StudentError.objects.count(),1)
  self.assertTrue((Path(self.temp.name)/'student_errors'/f'{self.u.pk}.json').is_file())
  with patch('learning.chat_service.complete',return_value=value):send(self.u,'Я сложил длины катетов и получил 14',self.t.pk,str(a.pk))
  self.assertEqual(StudentError.objects.count(),1);self.assertEqual(StudentError.objects.get().tasks_solved,0)
 def test_free_chat_cannot_write_diagnosis(self):
  bad={**REPLY,'action':'diagnosis_candidate','diagnosis':{'error_key':'pythagoras:sum_lengths','description':'x','evidence':'Я сложил длины катетов'}}
  with patch('learning.chat_service.complete',return_value=bad):
   result=send(self.u,'Я сложил длины катетов и получил 14')
  self.assertTrue(result['unavailable']);self.assertFalse(StudentError.objects.exists())
 def control(self):
  a=self.active()
  for _ in range(3):
   act(self.u,self.t,'answer',a.pk,a.task.answer);act(self.u,self.t,'next',a.pk);a=current(a.run)
  return a
 def test_control_marks_before_call_and_failure_does_not_restore(self):
  a=self.control()
  def check(role,ctx,msgs):
   a.refresh_from_db();self.assertTrue(a.assisted);self.assertTrue(ctx['assisted']);raise AIUnavailable
  with patch('learning.chat_service.complete',side_effect=check):send(self.u,'Помоги решить',self.t.pk,str(a.pk))
  a.refresh_from_db();self.assertTrue(a.assisted)
  act(self.u,self.t,'answer',a.pk,a.task.answer)
  a.run.refresh_from_db();self.assertEqual(a.run.completed,3)
 def test_technical_is_local_and_keeps_independence(self):
  a=self.control()
  with patch('learning.chat_service.complete') as api:send(self.u,'Как вводить ответ?',self.t.pk,str(a.pk))
  api.assert_not_called();a.refresh_from_db();self.assertFalse(a.assisted)
 def test_late_diagnosis_not_applied_to_new_task(self):
  a=self.active();act(self.u,self.t,'answer',a.pk,'999')
  value={**REPLY,'action':'diagnosis_candidate','diagnosis':{'error_key':'pythagoras:sum_lengths','description':'Сложение катетов','evidence':'Я сложил длины катетов'}}
  def move(*args):
   act(self.u,self.t,'answer',a.pk,a.task.answer);act(self.u,self.t,'next',a.pk);return value
  with patch('learning.chat_service.complete',side_effect=move):
   result=send(self.u,'Я сложил длины катетов и получил 14',self.t.pk,str(a.pk))
  self.assertTrue(result['late']);self.assertFalse(StudentError.objects.exists())
 def test_numeric_explanation_not_saved(self):
  a=self.active();act(self.u,self.t,'answer',a.pk,'999')
  with patch('learning.chat_service.complete',return_value=REPLY):send(self.u,'14',self.t.pk,str(a.pk))
  self.assertFalse(StudentError.objects.exists())
 def test_foreign_quote_and_stale_context_rejected(self):
  foreign=ChatMessage.objects.create(conversation=conversation(self.other),role='user',text='секрет')
  with self.assertRaises(ChatConflict):send(self.u,'Что это?',quote={'id':foreign.pk,'text':'секрет'})
  a=self.active()
  with self.assertRaises(ChatConflict):send(self.u,'Привет',self.t.pk,'outdated')
 def test_explicit_old_quote_added_only_itself(self):
  c=conversation(self.u);old=ChatMessage.objects.create(conversation=c,role='assistant',text='Теорема Пифагора. Остальной архив.')
  for i in range(20):ChatMessage.objects.create(conversation=c,role='user',text=f'recent{i}')
  with patch('learning.chat_service.complete',return_value=REPLY) as api:send(self.u,'Объясни',quote={'id':old.pk,'text':'Теорема Пифагора.'})
  self.assertIn('Теорема Пифагора.',str(api.call_args.args[2]));self.assertNotIn('Остальной архив',str(api.call_args.args[2]))
 def test_photo_confirmation_owner_and_version(self):
  photo=ChatPhoto.objects.create(conversation=conversation(self.u),transcription='x+1=3',readable=True)
  self.client.force_login(self.other)
  self.assertEqual(self.client.post('/api/chat/confirm',data=json.dumps({'id':str(photo.pk),'version':1}),content_type='application/json').status_code,404)
  self.client.force_login(self.u)
  self.assertEqual(self.client.post('/api/chat/confirm',data=json.dumps({'id':str(photo.pk),'version':2}),content_type='application/json').status_code,409)
  self.assertEqual(self.client.post('/api/chat/confirm',data=json.dumps({'id':str(photo.pk),'version':1}),content_type='application/json').status_code,200)
  photo.refresh_from_db();self.assertTrue(photo.confirmed)
 def test_pending_photo_blocks_help_until_confirmation(self):
  photo=ChatPhoto.objects.create(conversation=conversation(self.u),transcription='x+1=3',readable=True)
  with patch('learning.chat_service.complete') as api,self.assertRaises(ChatConflict):send(self.u,'Реши')
  api.assert_not_called()
 def test_invalid_photo_and_no_auth(self):
  self.assertEqual(self.client.get('/api/chat').status_code,401)
  self.client.force_login(self.u)
  self.assertEqual(self.client.post('/api/chat/upload',{'photo':io.BytesIO(b'not image')}).status_code,400)
 def test_api_csrf(self):
  c=Client(enforce_csrf_checks=True);c.force_login(self.u)
  self.assertEqual(c.post('/api/chat/send',data='{}',content_type='application/json').status_code,403)

 def test_confirmed_own_photo_does_not_replace_platform_context(self):
  ChatPhoto.objects.create(conversation=conversation(self.u),confirmed=True,readable=True,transcription='Old private photo task')
  a=self.active()
  with patch('learning.chat_service.complete',return_value=REPLY) as api:send(self.u,'С чего начать?',self.t.pk,str(a.pk))
  context=api.call_args.args[1];self.assertNotIn('photo',context);self.assertEqual(context['active_task_id'],str(a.pk))
 def test_uploaded_photo_is_private_and_waits_for_confirmation(self):
  from PIL import Image
  from django.core.files.uploadedfile import SimpleUploadedFile
  buffer=io.BytesIO();Image.new('RGB',(60,40),'white').save(buffer,format='PNG')
  self.client.force_login(self.u)
  value={**REPLY,'message':'x + 1 = 3. Я правильно прочитал задачу?','action':'confirm_photo'}
  with patch('learning.chat_service.complete',return_value=value) as api:
   response=self.client.post('/api/chat/upload',{'photo':SimpleUploadedFile('task.png',buffer.getvalue(),content_type='image/png'),'type':'','attempt':''})
  self.assertEqual(response.status_code,200)
  self.assertEqual(api.call_args.args[0],'photo')
  photo=ChatPhoto.objects.get();self.assertFalse(photo.confirmed)
  self.assertEqual(self.client.get(f'/api/chat/photos/{photo.pk}').status_code,200)
  self.client.force_login(self.other)
  self.assertEqual(self.client.get(f'/api/chat/photos/{photo.pk}').status_code,404)
  self.assertFalse(StudentError.objects.exists())
 def test_bad_confirmation_id_rejected(self):
  self.client.force_login(self.u)
  self.assertEqual(self.client.post('/api/chat/confirm',data=json.dumps({'id':'invalid','version':1}),content_type='application/json').status_code,400)
 def test_dismissed_photo_does_not_leak_unconfirmed_statement(self):
  c=conversation(self.u);photo=ChatPhoto.objects.create(conversation=c,transcription='PRIVATE_UNCONFIRMED_CONDITION',readable=True)
  ChatMessage.objects.create(conversation=c,role='assistant',text=photo.transcription,photo=photo)
  self.client.force_login(self.u)
  r=self.client.post('/api/chat/photo-dismiss',data=json.dumps({'id':str(photo.pk),'version':1}),content_type='application/json')
  self.assertEqual(r.status_code,200)
  with patch('learning.chat_service.complete',return_value=REPLY) as api:send(self.u,'Объясни квадратные уравнения')
  self.assertNotIn('PRIVATE_UNCONFIRMED_CONDITION',str(api.call_args.args[2]))
  self.assertNotIn('photo',api.call_args.args[1])

 def test_provider_uses_only_new_endpoint_and_private_key(self):
  from .ai_provider import complete
  from types import SimpleNamespace
  (Path(self.temp.name)/'aijuju.key').write_text('synthetic-test-credential')
  response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(REPLY)}}]}
  with patch.dict('os.environ',{'AIJUJU_API_KEY':''}),patch('learning.ai_provider.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(response)+'\n200')) as curl:
   value=complete('free_chat',{'mode':'free_chat','user_id':'test','active_task_id':None},[{'role':'user','content':'Помоги понять дроби'}])
  self.assertEqual(value,REPLY)
  args=curl.call_args.args[0]
  self.assertEqual(args[-1],'https://api.aijuju.rest/v1/chat/completions')
  self.assertNotIn('synthetic-test-credential',str(args))
  self.assertEqual(json.loads(curl.call_args.kwargs['input'])['model'],'gpt-6.1-sol')
  self.assertFalse(list(Path(self.temp.name).glob('ai-auth-*')))

 def test_provider_rejects_failed_http_without_exposing_response(self):
  from .ai_provider import complete
  from types import SimpleNamespace
  with patch.dict('os.environ',{'AIJUJU_API_KEY':'synthetic-test-credential'}),patch('learning.ai_provider.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='private provider detail\n401')):
   with self.assertRaises(AIUnavailable) as failure:complete('free_chat',{},[])
  self.assertNotIn('private provider detail',str(failure.exception))
