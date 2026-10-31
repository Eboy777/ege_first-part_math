from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from learning.models import TaskType,TrainingRun,Progress,Attempt
from learning.training import available
from learning.reviews import schedule

class Command(BaseCommand):
    help='Add labelled review fixtures to a local test account without replacing existing work.'
    def add_arguments(self,parser):parser.add_argument('username',choices=['student_a','student_b'])
    @transaction.atomic
    def handle(self,*args,**options):
        user=get_user_model().objects.get(username=options['username'])
        existing=Progress.objects.filter(user=user,is_demo=True,completed=5,task_type__number__exam_id='ege_profile_2026').count()
        if existing>=3:self.stdout.write('Демонстрационные типы уже подготовлены.');return
        now=timezone.now()
        types=TaskType.objects.filter(number__exam_id='ege_profile_2026',bank_tasks__status='published',bank_tasks__answer_verified=True,bank_tasks__candidate__rights_status='approved').annotate(total=Count('bank_tasks')).filter(total__gte=9).exclude(pk__in=TrainingRun.objects.filter(user=user).values('task_type_id')).order_by('number__number','position')
        chosen=list(types[:3])
        if len(chosen)<3:raise CommandError('Недостаточно свободных типов с проверенными задачами.')
        for index,t in enumerate(chosen):
            mastered=now-timedelta(days=[10,50,2][index]);run=TrainingRun.objects.create(user=user,task_type=t,completed=5,mastered_at=mastered)
            Progress.objects.update_or_create(user=user,task_type=t,defaults={'completed':5,'is_demo':True})
            for stage in range(1,6):Attempt.objects.create(run=run,task=available(run).first(),stage=stage,status='solved',credited_at=mastered)
            seven,thirty,ninety=schedule(run)
            if index==1:
                done=now-timedelta(days=40);seven.started_at=done;seven.completed_at=done;seven.completed=2;seven.save();thirty.due_at=done+timedelta(days=30);thirty.save()
                for stage in (4,5):Attempt.objects.create(run=run,review=seven,task=available(run).first(),stage=stage,status='solved',credited_at=done)
            self.stdout.write(f'{t.pk}: 5/5; '+['пора повторить 7 дней','пора повторить 30 дней','повторение 7 дней запланировано'][index])
