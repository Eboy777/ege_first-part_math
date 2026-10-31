from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.exceptions import ValidationError
from .models import TaskType,Candidate,BankTask,TrainingRun,Progress,Attempt,AnswerSubmission
from .training import act,current
import io

class TrainingTests(TestCase):
 @classmethod
 def setUpTestData(cls):
  call_command('load_catalog',stdout=io.StringIO())
  cls.u=get_user_model().objects.create_user('learner')
  cls.other=get_user_model().objects.create_user('other')
  cls.t=TaskType.objects.get(pk='right-triangle')
  for i in range(9):
   c=Candidate.objects.create(source_url=f'https://example.org/{i}',source_task_id=str(i),source='test',task_type=cls.t,rights_status='approved',license_or_permission='test fixture')
   BankTask.objects.create(id=f'test-{i}',candidate=c,task_type=cls.t,statement=f'Вычислите {i}+2',answer=str(i+2),answer_verified=True,verification_notes='test fixture',family_key=f'f{i}',status='published')
 def attempt(self):return current(TrainingRun.objects.get(user=self.u,task_type=self.t))
 def submit(self,value):return act(self.u,self.t,'answer',self.attempt().pk,value)
 def test_five_stages_and_idempotency(self):
  act(self.u,self.t,'start');seen=[]
  for stage in range(1,6):
   a=self.attempt();seen.append(a.task_id)
   self.assertEqual(a.stage,stage)
   self.submit(a.task.answer)
   self.submit(a.task.answer)
   self.assertEqual(Progress.objects.get(user=self.u,task_type=self.t).completed,stage)
   if stage<5:act(self.u,self.t,'next',a.pk)
  self.assertEqual(len(set(seen)),5)
  self.assertEqual(AnswerSubmission.objects.count(),5)
  self.assertIsNotNone(TrainingRun.objects.get(user=self.u).mastered_at)
 def test_invalid_and_wrong_do_not_advance(self):
  act(self.u,self.t,'start');a=self.attempt()
  self.submit('abc');self.assertEqual(AnswerSubmission.objects.count(),0)
  self.submit('999');self.assertEqual(self.attempt().status,'incorrect')
  act(self.u,self.t,'next',a.pk);self.assertEqual(self.attempt().pk,a.pk)
  self.submit(a.task.answer);self.assertEqual(TrainingRun.objects.get(user=self.u).completed,1)
 def to_control(self):
  act(self.u,self.t,'start')
  for _ in range(3):
   a=self.attempt();self.submit(a.task.answer);act(self.u,self.t,'next',a.pk)
 def test_control_correction_independent(self):
  self.to_control();a=self.attempt();self.submit('999');self.assertFalse(self.attempt().assisted)
  self.submit(a.task.answer);self.assertEqual(TrainingRun.objects.get(user=self.u).completed,4)
 def test_theory_invalidates_persistently(self):
  self.to_control();a=self.attempt();act(self.u,self.t,'theory',a.pk)
  self.submit(a.task.answer);self.assertEqual(TrainingRun.objects.get(user=self.u).completed,3)
  act(self.u,self.t,'next',a.pk);b=self.attempt()
  self.assertNotEqual(a.task_id,b.task_id);self.assertEqual(b.stage,4)
  self.assertFalse(b.assisted)
 def test_assisted_flag_cannot_credit_control(self):
  self.to_control();a=self.attempt();a.assisted=True;a.save()
  self.submit(a.task.answer);self.assertIsNone(self.attempt().credited_at)
 def test_stale_and_other_users(self):
  act(self.u,self.t,'start');a=self.attempt();act(self.other,self.t,'start')
  self.assertIn('не текущая',act(self.other,self.t,'answer',a.pk,a.task.answer))
  self.submit(a.task.answer);act(self.u,self.t,'next',a.pk)
  self.assertIn('не текущая',act(self.u,self.t,'answer',a.pk,a.task.answer))
 def test_views_and_secret_answer_not_sent(self):
  self.client.force_login(self.u)
  path='/exam/2026/types/right-triangle'
  self.client.post(path,{'action':'start'})
  r=self.client.get(path);self.assertEqual(r.status_code,200)
  self.assertNotIn('accepted_answers',r.content.decode())
  self.assertNotIn('credited_at',r.content.decode())
  a=self.attempt();self.client.post(path,{'action':'answer','attempt':str(a.pk),'answer':a.task.answer+',0'})
  self.assertEqual(self.attempt().status,'solved')

 def test_stale_theory_request_cannot_reveal_current_control(self):
  self.to_control();self.client.force_login(self.u)
  path='/exam/2026/types/right-triangle'
  self.client.post(path,{'action':'theory','attempt':'stale'})
  response=self.client.get(path)
  self.assertFalse(response.context['show_theory'])
  self.assertNotContains(response,'class="formula"')
  self.assertFalse(self.attempt().assisted)
