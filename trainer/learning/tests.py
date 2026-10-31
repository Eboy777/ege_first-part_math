import io
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone
from .models import ExamVersion, ExamNumber, TaskType, Progress, LoginFailure

class StageTwoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('load_catalog',stdout=io.StringIO())
        cls.alice=get_user_model().objects.create_user('alice',password='ExamplePassword-7bq!')
        cls.bob=get_user_model().objects.create_user('bob',password='ExamplePassword-8cr!')
        cls.type=TaskType.objects.get(pk='right-triangle')
        cls.a=Progress.objects.create(user=cls.alice,task_type=cls.type,completed=2,is_demo=True)
        cls.b=Progress.objects.create(user=cls.bob,task_type=cls.type,completed=4,is_demo=True)

    def test_all_student_pages_require_login(self):
        for path in ['/', '/exam/2026/tasks/1','/exam/2026/types/right-triangle','/mistakes']:
            with self.subTest(path=path):
                response=self.client.get(path)
                self.assertEqual(response.status_code,302)
                self.assertTrue(response.url.startswith('/login?next='))

    def test_api_requires_authentication(self):
        for path in ['/api/me','/api/progress',f'/api/progress/{self.a.pk}']:
            self.assertEqual(self.client.get(path).status_code,401)

    def test_login_rotation_cookie_and_logout(self):
        self.client.get('/login')
        old=self.client.session.session_key
        response=self.client.post('/login',{'username':'alice','password':'ExamplePassword-7bq!'})
        self.assertEqual(response.status_code,302)
        self.assertNotEqual(old,self.client.session.session_key)
        self.assertTrue(response.cookies['pyaterka_session']['httponly'])
        self.assertEqual(response.cookies['pyaterka_session']['samesite'],'Lax')
        self.assertEqual(self.client.get('/logout').status_code,405)
        self.assertEqual(self.client.post('/logout').status_code,302)
        self.assertEqual(self.client.get('/api/me').status_code,401)

    def test_login_errors_generic(self):
        a=self.client.post('/login',{'username':'unknown','password':'wrong'})
        b=self.client.post('/login',{'username':'alice','password':'wrong'})
        self.assertEqual(a.status_code,400)
        self.assertEqual(b.status_code,400)
        self.assertContains(a,'Неверный логин или пароль',status_code=400)
        self.assertContains(b,'Неверный логин или пароль',status_code=400)

    def test_login_rate_limit_and_expiry(self):
        for _ in range(5):
            self.client.post('/login',{'username':'alice','password':'wrong'})
        self.assertEqual(self.client.post('/login',{'username':'alice','password':'ExamplePassword-7bq!'}).status_code,429)
        LoginFailure.objects.update(window_start=timezone.now()-timedelta(minutes=16))
        self.assertEqual(self.client.post('/login',{'username':'alice','password':'ExamplePassword-7bq!'}).status_code,302)

    def test_ip_rate_limit_cannot_be_bypassed_by_changing_login(self):
        from .stage2_views import throttle_keys
        key=throttle_keys(self.client.get('/login').wsgi_request,'any')[1][0]
        LoginFailure.objects.create(key=key,count=30,window_start=timezone.now())
        self.assertEqual(self.client.post('/login',{'username':'bob','password':'ExamplePassword-8cr!'}).status_code,429)

    def test_csrf_enforced_on_login_and_logout(self):
        c=Client(enforce_csrf_checks=True)
        c.get('/login')
        self.assertEqual(c.post('/login',{'username':'alice','password':'ExamplePassword-7bq!'}).status_code,403)
        token=c.cookies['csrftoken'].value
        self.assertEqual(c.post('/login',{'username':'alice','password':'ExamplePassword-7bq!','csrfmiddlewaretoken':token}).status_code,302)
        self.assertEqual(c.post('/logout').status_code,403)
        self.assertEqual(c.post('/logout',{'csrfmiddlewaretoken':c.cookies['csrftoken'].value}).status_code,302)

    def test_external_login_redirect_rejected(self):
        response=self.client.post('/login',{'username':'alice','password':'ExamplePassword-7bq!','next':'https://example.org/steal'})
        self.assertEqual(response.url,'/')

    def test_two_users_get_only_their_progress(self):
        self.client.force_login(self.alice)
        values=self.client.get('/api/progress').json()['progress']
        self.assertEqual([row['completed'] for row in values],[2])
        self.assertEqual(self.client.get(f'/api/progress/{self.b.pk}').status_code,404)
        self.assertEqual(self.client.get(f'/api/progress/{self.a.pk}').json()['completed'],2)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.get('/api/progress').json()['progress'][0]['completed'],4)
        self.assertEqual(self.client.get(f'/api/progress/{self.a.pk}').status_code,404)

    def test_server_rendered_progress_is_personal(self):
        self.client.force_login(self.alice)
        response=self.client.get('/exam/2026/types/right-triangle')
        self.assertContains(response,'2/5')
        self.assertNotContains(response,'4/5')
        self.assertNotContains(response,'Демонстрационный прогресс')
        self.assertContains(response,'Тренироваться →')

    def test_student_cannot_set_progress_or_impersonate(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post('/api/progress',{'user_id':self.bob.pk,'completed':5}).status_code,405)
        self.assertEqual(self.client.get(f'/api/progress?user_id={self.bob.pk}').status_code,400)
        self.a.refresh_from_db()
        self.assertEqual(self.a.completed,2)

    def test_blocked_account_and_existing_session(self):
        self.client.force_login(self.alice)
        self.alice.is_active=False
        self.alice.save()
        self.assertEqual(self.client.get('/api/me').status_code,401)
        self.assertEqual(self.client.post('/login',{'username':'alice','password':'ExamplePassword-7bq!'}).status_code,400)

    def test_reset_password_invalidates_existing_session(self):
        self.client.force_login(self.alice)
        self.alice.set_password('NewPassword-27ct!')
        self.alice.save()
        self.assertEqual(self.client.get('/api/me').status_code,401)

    def test_catalog_idempotent_and_versioned(self):
        call_command('load_catalog',stdout=io.StringIO())
        self.assertEqual(ExamNumber.objects.filter(exam_id='2026').count(),12)
        self.assertEqual(TaskType.objects.count(),2)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get('/exam/2027/tasks/1').status_code,404)
        self.assertEqual(self.client.get('/exam/2026/tasks/13').status_code,404)
        for number in ExamNumber.objects.all():
            self.assertEqual(self.client.get(f'/exam/2026/tasks/{number.number}').status_code,200)

    def test_static_asset_and_runtime_not_exposed_by_application(self):
        self.client.force_login(self.alice)
        for path in ['/.runtime/trainer.sqlite3','/.runtime/secret.key','/trainer/learning/data/catalog.json','/register','/admin/']:
            self.assertEqual(self.client.get(path).status_code,404)

    def test_password_hashed_and_private_cache_headers(self):
        self.assertNotEqual(self.alice.password,'ExamplePassword-7bq!')
        self.assertTrue(self.alice.check_password('ExamplePassword-7bq!'))
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get('/api/me')['Cache-Control'],'no-store, private')

    def test_template_escapes_student_name(self):
        self.alice.first_name='<script>alert(1)</script>'
        self.alice.save()
        self.client.force_login(self.alice)
        response=self.client.get('/')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_progress_database_constraints(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            Progress.objects.filter(pk=self.a.pk).update(completed=6)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Progress.objects.create(user=self.alice,task_type=self.type)
