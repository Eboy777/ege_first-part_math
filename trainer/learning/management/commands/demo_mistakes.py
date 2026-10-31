from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from learning.models import Attempt,StudentError
from learning.error_store import ERROR_CATALOG,project_errors

class Command(BaseCommand):
    help='Seed example errors for a test account without overwriting existing errors.'
    def add_arguments(self,parser):parser.add_argument('username',choices=['student_a','student_b'])
    @transaction.atomic
    def handle(self,*args,**options):
        user=get_user_model().objects.get(username=options['username'])
        attempt=Attempt.objects.filter(run__user=user).first()
        if not attempt:raise CommandError('Сначала подготовьте тестовые задачи ученика.')
        fixtures=[('pythagoras:sum_lengths','Сложил катеты вместо суммы квадратов.',0),('fractions:addition','Сложил числители и знаменатели отдельно.',1),('probability:complement','Взял вероятность противоположного события.',0),('arithmetic:sign','Потерял минус при переносе слагаемого.',2),('powers:addition','Сложил показатели при сложении степеней.',0),('sqrt:square_modulus','Из корня квадрата получил отрицательное число.',3)]
        for i,(key,evidence,count) in enumerate(fixtures):
            e,created=StudentError.objects.get_or_create(user=user,error_key=key,defaults={'description':ERROR_CATALOG[key],'evidence':'Тестовые данные: '+evidence,'attempt':attempt,'tasks_solved':count})
            if created:StudentError.objects.filter(pk=e.pk).update(first_detected_at=timezone.now()-timedelta(days=12-i))
        transaction.on_commit(lambda:project_errors(user.pk));self.stdout.write('Тестовые ошибки добавлены; существующие записи сохранены.')
