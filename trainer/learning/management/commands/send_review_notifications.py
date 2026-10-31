import time
from django.core.management.base import BaseCommand
from learning.notifications import send_due_notifications

class Command(BaseCommand):
    help='Send one notification per new due checkpoint to opted-in browsers.'
    def add_arguments(self,parser):parser.add_argument('--watch',action='store_true',help='Check every minute while this process runs.')
    def handle(self,*args,**options):
        while True:
            sent=send_due_notifications()
            if sent:self.stdout.write(f'Уведомлений отправлено: {sent}')
            if not options['watch']:break
            try:time.sleep(60)
            except KeyboardInterrupt:break
