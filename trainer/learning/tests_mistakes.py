import tempfile,json
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase,Client,override_settings
from django.utils import timezone
from .tests_training import TrainingTests as Fixtures
from .models import StudentError,Conversation,ChatMessage,MistakeExercise,TrainingRun,Progress
from .training import act,current
from .mistakes_service import send,conversation,options
from .chat_service import ChatConflict
from .ai_provider import AIUnavailable

CANDIDATE={'message':'Не показывать скрытый ответ','action':'exercise_candidate','diagnosis':None,'exercise':{'kind':'calculation','statement':'Вычисли 1/2 + 1/3.','answer':'5/6','explanation':'Общий знаменатель 6.','check':'3/6+2/6=5/6, проверено повторно.'},'assessment':None}
def assessment(verdict):return {'message':'Попробуй общий знаменатель.' if verdict!='success' else 'Верно.','action':'exercise_assessment','diagnosis':None,'exercise':None,'assessment':{'verdict':verdict,'evidence':'Проверено по сохранённому эталону.'}}
REPLY={'message':'Какой общий знаменатель?','action':'reply','diagnosis':None,'exercise':None,'assessment':None}

class MistakesTests(TestCase):
 @classmethod
 def setUpTestData(cls):
  Fixtures.setUpTestData.__func__(cls);act(cls.u,cls.t,'start');a=current(TrainingRun.objects.get(user=cls.u,task_type=cls.t))
  cls.error=StudentError.objects.create(user=cls.u,error_key='fractions:addition',description='Ошибка сложения дробей',evidence='Сложил знаменатели',attempt=a)
  cls.foreign=StudentError.objects.create(user=cls.other,error_key='arithmetic:sign',description='Знак',evidence='Минус',attempt=a)
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.override=override_settings(STATE_DIR=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)
 def generate(self):
  with patch('learning.mistakes_service.complete',return_value=CANDIDATE):send(self.u,'select',error_id=self.error.pk)
  return MistakeExercise.objects.get(status='active')
 def test_generate_hidden_reference_and_last_ten_separate(self):
  main=Conversation.objects.create(user=self.u,kind='main');ChatMessage.objects.create(conversation=main,role='user',text='PRIVATE MAIN CHAT')
  conv=conversation(self.u)
  for i in range(16):ChatMessage.objects.create(conversation=conv,role='user',text=f'old-{i}')
  with patch('learning.mistakes_service.complete',return_value=CANDIDATE) as api:send(self.u,'select',error_id=self.error.pk)
  role,ctx,messages=api.call_args.args;self.assertEqual(role,'mistakes_generate');self.assertEqual(ctx['mode'],'mistakes');self.assertNotIn('PRIVATE MAIN CHAT',str(messages));self.assertEqual(sum(m['role']!='system' for m in messages),10)
  self.client.force_login(self.u);data=self.client.get('/api/mistakes').json();self.assertNotIn('answer',data['active']);self.assertNotIn('5/6',json.dumps(data));self.assertEqual(data['messages'][-1]['text'],CANDIDATE['exercise']['statement'])
 def test_success_once_and_private_projection_no_training_change(self):
  ex=self.generate();run=TrainingRun.objects.get(user=self.u);before=run.completed
  with patch('learning.mistakes_service.complete',return_value=assessment('success')),self.captureOnCommitCallbacks(execute=True):send(self.u,'answer','5/6',exercise_id=str(ex.pk))
  self.error.refresh_from_db();self.assertEqual(self.error.tasks_solved,1);ex.refresh_from_db();self.assertEqual(ex.status,'completed');run.refresh_from_db();self.assertEqual(run.completed,before);self.assertFalse(Progress.objects.exists())
  self.assertEqual(json.loads((Path(self.temp.name)/'student_errors'/f'{self.u.pk}.json').read_text())['errors'][0]['tasks_solved'],1)
  with self.assertRaises(ChatConflict):send(self.u,'answer','5/6',exercise_id=str(ex.pk))
  self.error.refresh_from_db();self.assertEqual(self.error.tasks_solved,1)
 def test_wrong_and_insufficient_stay_same(self):
  ex=self.generate()
  for verdict in ('incorrect','insufficient'):
   with patch('learning.mistakes_service.complete',return_value=assessment(verdict)):send(self.u,'answer','1/5',exercise_id=str(ex.pk))
  ex.refresh_from_db();self.assertEqual(ex.status,'active');self.assertEqual(ex.failed_attempts,2);self.error.refresh_from_db();self.assertEqual(self.error.tasks_solved,0)
 def test_help_and_understood_never_credit(self):
  ex=self.generate()
  with patch('learning.mistakes_service.complete',return_value=REPLY) as api:
   send(self.u,'help','Помоги',exercise_id=str(ex.pk));self.assertEqual(api.call_args.args[0],'mistakes_tutor')
   send(self.u,'answer','понял',exercise_id=str(ex.pk));self.assertEqual(api.call_args.args[0],'mistakes_tutor')
  self.error.refresh_from_db();self.assertEqual(self.error.tasks_solved,0)
 def test_failure_preserves_exercise_and_count(self):
  ex=self.generate()
  with patch('learning.mistakes_service.complete',side_effect=AIUnavailable):self.assertTrue(send(self.u,'answer','5/6',exercise_id=str(ex.pk))['unavailable'])
  ex.refresh_from_db();self.assertEqual(ex.status,'active');self.error.refresh_from_db();self.assertEqual(self.error.tasks_solved,0)
 def test_foreign_stale_and_changed_selection(self):
  with self.assertRaises(ChatConflict):send(self.u,'select',error_id=self.foreign.pk)
  ex=self.generate()
  with self.assertRaises(ChatConflict):send(self.other,'answer','5/6',exercise_id=str(ex.pk))
  with self.assertRaises(ChatConflict):send(self.u,'select',error_id=self.error.pk)
  with patch('learning.mistakes_service.complete',return_value=CANDIDATE):send(self.u,'select',error_id=self.error.pk,exercise_id=str(ex.pk))
  ex.refresh_from_db();self.assertEqual(ex.status,'abandoned');self.assertEqual(MistakeExercise.objects.filter(status='active').count(),1)
 def test_top_five_sorted_and_recomputed(self):
  a=self.error.attempt
  for i in range(6):StudentError.objects.create(user=self.u,error_key=f'test:{i}',description=f'Ошибка {i}',evidence='test',attempt=a,tasks_solved=i)
  self.assertEqual(len(options(self.u)),5);self.assertEqual(options(self.u)[0].pk,self.error.pk)
  ex=self.generate()
  with patch('learning.mistakes_service.complete',return_value=assessment('success')):send(self.u,'answer','5/6',exercise_id=str(ex.pk))
  self.assertNotEqual(options(self.u)[0].pk,self.error.pk)
 def test_concept_question_success(self):
  candidate={**CANDIDATE,'exercise':{**CANDIDATE['exercise'],'kind':'concept','statement':'Что требуется сделать со знаменателями перед сложением дробей?','answer':'Привести к общему знаменателю'}}
  with patch('learning.mistakes_service.complete',return_value=candidate):send(self.u,'select',error_id=self.error.pk)
  ex=MistakeExercise.objects.get(status='active')
  with patch('learning.mistakes_service.complete',return_value=assessment('success')):send(self.u,'answer','Привести к общему знаменателю',exercise_id=str(ex.pk))
  self.error.refresh_from_db();self.assertEqual(self.error.tasks_solved,1)
 def test_api_csrf_empty_auth_and_restore(self):
  c=Client(enforce_csrf_checks=True);c.force_login(self.u);self.assertEqual(c.post('/api/mistakes/send',{'operation':'select'},content_type='application/json').status_code,403)
  self.assertEqual(Client().get('/api/mistakes').status_code,401)
  self.client.force_login(self.other);self.assertEqual(len(self.client.get('/api/mistakes').json()['options']),1)
  ex=self.generate();self.client.force_login(self.u);self.assertEqual(self.client.get('/api/mistakes').json()['active']['id'],str(ex.pk))
  self.assertEqual(self.client.post('/api/mistakes/send',{'text':''},content_type='application/json').status_code,400)
 def test_busy_does_not_duplicate_and_empty_menu(self):
  conv=conversation(self.u);conv.busy_until=timezone.now()+__import__('datetime').timedelta(seconds=70);conv.save()
  with self.assertRaises(ChatConflict):send(self.u,'select',error_id=self.error.pk)
  self.assertFalse(MistakeExercise.objects.exists());StudentError.objects.filter(user=self.other).delete();self.client.force_login(self.other);data=self.client.get('/api/mistakes').json();self.assertEqual(data['options'],[]);self.assertIn('пока нет',data['messages'][0]['text'])
