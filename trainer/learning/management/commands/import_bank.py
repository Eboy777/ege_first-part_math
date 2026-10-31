import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from learning.models import Candidate, BankTask, TaskType

class Command(BaseCommand):
    help = 'Атомарный импорт разрешённых оригиналов. Не скачивает и не генерирует материалы.'
    def add_arguments(self, parser):
        parser.add_argument('manifest', type=Path)
    def handle(self, *args, **options):
        try:
            rows = json.loads(options['manifest'].read_text())
            if not isinstance(rows, list):
                raise ValueError('Манифест должен быть списком задач')
            with transaction.atomic():
                for row in rows:
                    t = TaskType.objects.get(type_id=row['type_id'],number__exam_id=row['exam'],number__number=row['number'])
                    if row.get('rights_status') != 'approved':
                        raise ValueError('Материалы с pending/denied нельзя локально импортировать')
                    c, _ = Candidate.objects.get_or_create(source_url=row['source_url'],source_task_id=row['source_task_id'],defaults={'source':row['source'],'task_type':t,'rights_status':'approved','license_or_permission':row['license_or_permission']})
                    # Apply reviewed classification only to a not-yet-imported candidate.
                    # Rights and existing published tasks remain unchanged.
                    if c.task_type_id != t.pk and not BankTask.objects.filter(candidate=c).exists():
                        c.task_type = t
                        c.save(update_fields=['task_type'])
                    # Existing rights are never silently overwritten by an import.
                    fields = ['statement','statement_format','answer','accepted_answers','image_paths','requires_illustration','answer_verified','illustration_verified','verification_notes','family_key','status']
                    task = BankTask(id=row['id'],candidate=c,task_type=t,**{k:row[k] for k in fields if k in row})
                    task.full_clean(exclude=['content_hash'])
                    task.validate_unique()
                    task.save(force_insert=True)
            self.stdout.write(self.style.SUCCESS(f'Импортировано: {len(rows)}'))
        except (ValueError, KeyError, OSError, ValidationError, IntegrityError, TaskType.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
