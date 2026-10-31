import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from learning.models import ExamVersion, Section, ExamNumber, TaskType

class Command(BaseCommand):
    help = 'Load an idempotent stage-2 catalog; contains theory, no task bank.'
    def add_arguments(self, parser):
        parser.add_argument('--file', type=Path, default=Path(__file__).resolve().parents[2] / 'data' / 'catalog.json')
    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(options['file'].read_text())
        numbers = [n['number'] for g in data['sections'] for n in g['numbers']]
        if len(set(numbers)) != len(numbers):
            raise CommandError('Duplicate exam numbers')
        exam, _ = ExamVersion.objects.update_or_create(code=data['version'], defaults={'title':data['title']})
        for position, group in enumerate(data['sections']):
            section, _ = Section.objects.update_or_create(exam=exam,slug=group['slug'],defaults={'title':group['title'],'accent':group['accent'],'position':position})
            for n in group['numbers']:
                number, _ = ExamNumber.objects.update_or_create(exam=exam,number=n['number'],defaults={'section':section,'title':n['title']})
                for index,t in enumerate(n.get('types',[])):
                    existing = TaskType.objects.filter(pk=t['id']).first()
                    if existing and existing.number_id != number.pk:
                        raise CommandError('Type ID belongs to another exam number')
                    TaskType.objects.update_or_create(slug=t['id'], defaults={'number':number,'position':index,'title':t['title'],'theory':t['theory'],'formula':t['formula'],'example':t['example'],'method_reference':t.get('method_reference','')})
        self.stdout.write(self.style.SUCCESS(f'Catalog {exam.pk}: {len(numbers)} numbers, {TaskType.objects.filter(number__exam=exam).count()} types. No tasks imported.'))
