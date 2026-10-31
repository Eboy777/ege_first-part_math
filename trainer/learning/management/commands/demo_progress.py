from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from learning.models import TaskType, Progress
class Command(BaseCommand):
    help='Set clearly marked demonstration progress; not a student-facing endpoint.'
    def add_arguments(self,parser):
        parser.add_argument('login')
        parser.add_argument('type_id')
        parser.add_argument('completed',type=int,choices=range(6))
    def handle(self,*args,**o):
        try:
            user=get_user_model().objects.get(username=o['login'])
            task_type=TaskType.objects.get(pk=o['type_id'])
        except (get_user_model().DoesNotExist,TaskType.DoesNotExist):
            raise CommandError('Student or type not found')
        Progress.objects.update_or_create(user=user,task_type=task_type,defaults={'completed':o['completed'],'is_demo':True})
        self.stdout.write('Saved demonstration progress to database.')
