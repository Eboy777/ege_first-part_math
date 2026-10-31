from django.test import TestCase,Client
from django.contrib.auth import get_user_model

class MobileLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password='Synthetic-Mobile-Password-42!'
        cls.user=get_user_model().objects.create_user('student_phone',password=cls.password)
    def test_phone_capitalized_username_and_spaces(self):
        r=self.client.post('/login',{'username':' Student_Phone ','password':self.password},HTTP_USER_AGENT='Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)')
        self.assertEqual(r.status_code,302)
        self.assertEqual(self.client.get('/api/me').json()['login'],'student_phone')
    def test_wrong_password_and_inactive_still_rejected(self):
        r=self.client.post('/login',{'username':'STUDENT_PHONE','password':self.password.lower()});self.assertEqual(r.status_code,400)
        self.user.is_active=False;self.user.save()
        r=self.client.post('/login',{'username':'Student_Phone','password':self.password});self.assertEqual(r.status_code,400)
    def test_password_spaces_not_silently_removed(self):
        r=self.client.post('/login',{'username':'student_phone','password':' '+self.password+' '});self.assertEqual(r.status_code,400)
    def test_authentication_still_requires_csrf(self):
        c=Client(enforce_csrf_checks=True)
        self.assertEqual(c.post('/login',{'username':'Student_Phone','password':self.password}).status_code,403)
