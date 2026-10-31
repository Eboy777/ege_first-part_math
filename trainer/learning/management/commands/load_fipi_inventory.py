import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from learning.models import Candidate

class Command(BaseCommand):
    help='Добавить метаданные кандидатов с кратким ответом из скачанного официального реестра.'
    def add_arguments(self,parser):
        parser.add_argument('inventory',type=Path)
    @transaction.atomic
    def handle(self,*args,**options):
        rows=json.loads(options['inventory'].read_text())
        count=0
        for row in rows:
            if not row['short_answer']:continue
            defaults={k:row[k] for k in ['source','rights_status','license_or_permission','notes']}
            defaults['notes']+=' GUID: '+row['guid']+'. Коды ФИПИ: '+'; '.join(row['source_codes'])
            Candidate.objects.get_or_create(source_url=row['source_url'],source_task_id=row['source_task_id'],defaults=defaults)
            count+=1
        self.stdout.write(f'Кандидатов с кратким ответом: {count}. Типы и ответы требуют проверки.')
