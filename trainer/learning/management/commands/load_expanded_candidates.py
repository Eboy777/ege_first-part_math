import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from learning.models import Candidate,TaskType
class Command(BaseCommand):
    help='Сохранить метаданные исследованных прототипов дополнительных источников.'
    def add_arguments(self,p):p.add_argument('inventory',type=Path)
    @transaction.atomic
    def handle(self,*args,**options):
        rows=json.loads(options['inventory'].read_text())
        for r in rows:
            t=TaskType.objects.get(type_id=r['type_id']) if r['type_id'] else None
            defaults={k:r[k] for k in ['source','rights_status','license_or_permission','notes']}
            defaults.update(task_type=t,notes=r['notes']+' Категории источника: '+','.join(map(str,r['source_categories']))+'; группы для проверки: '+', '.join(r['suggested_type_groups']))
            Candidate.objects.get_or_create(source_url=r['source_url'],source_task_id=r['source_task_id'],defaults=defaults)
        self.stdout.write(f'Записей прототипов: {len(rows)}. Кандидаты не считаются готовыми задачами.')
