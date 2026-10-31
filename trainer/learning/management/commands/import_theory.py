import re
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from learning.models import TaskType

SOURCE=Path(__file__).resolve().parents[2]/'data'/'theory_2026.md'
def plain(text):
    return text.strip().replace('**','').replace('`','')
def parse_theory(text):
    records=[]
    pattern=r'^## (\d+\.\d+)\. ([^\n]+)\n(.*?)(?=^## \d+\.\d+\. |^# |\Z)'
    for match in re.finditer(pattern,text,re.M|re.S):
        type_id,title,body=match.groups()
        def extract(pattern):
            m=re.search(pattern,body,re.S|re.M)
            if not m:raise CommandError(f'{type_id}: incomplete material')
            return plain(m.group(1))
        declared=extract(r'^\*\*ID:\*\* `([^`]+)`')
        if declared!=type_id:raise CommandError('Heading and type_id differ')
        theory=extract(r'### Короткая теория\s+(.*?)\s+### Алгоритм решения')
        algorithm=extract(r'### Алгоритм решения\s+(.*?)\s+### Разобранный пример')
        statement=extract(r'\*\*Задача\.\*\*\s*(.*?)\s*\*\*Решение:\*\*')
        solution=extract(r'\*\*Решение:\*\*\s*(.*?)\s*\*\*Ответ:\*\*')
        answer=extract(r'\*\*Ответ:\*\*\s*(.*?)\s*\*\*Типичная ошибка:\*\*')
        pitfall=extract(r'\*\*Типичная ошибка:\*\*\s*(.*?)\s*\*\*Иллюстрация:\*\*')
        steps=lambda value:[re.sub(r'^\d+\.\s*','',line.strip()) for line in value.splitlines() if line.strip()]
        records.append({'type_id':type_id,'title':title,'theory':theory,'example':{'statement':statement,'steps':steps(solution),'answer':answer,'algorithm':steps(algorithm),'pitfall':pitfall}})
    if len(records)!=56 or len({r['type_id'] for r in records})!=56:raise CommandError('Expected 56 unique type IDs')
    return records

class Command(BaseCommand):
    help='Import supplied theory by stable type_id, without modifying the bank or progress.'
    def add_arguments(self,parser):
        parser.add_argument('--file',type=Path,default=SOURCE)
        parser.add_argument('--dry-run',action='store_true')
    @transaction.atomic
    def handle(self,*args,**options):
        records=parse_theory(options['file'].read_text())
        types={t.type_id:t for t in TaskType.objects.filter(number__exam_id='ege_profile_2026')}
        if set(types)!={r['type_id'] for r in records}:raise CommandError('Theory IDs do not exactly match database catalog')
        for row in records:
            t=types[row['type_id']]
            if t.title.strip()!=row['title'].strip():raise CommandError(f'Title mismatch: {t.type_id}')
        if not options['dry_run']:
            for row in records:
                TaskType.objects.filter(pk=types[row['type_id']].pk).update(theory=row['theory'],formula='',example=row['example'])
        self.stdout.write(f"{'Validated' if options['dry_run'] else 'Imported'}: 56 types; bank and progress unchanged.")
