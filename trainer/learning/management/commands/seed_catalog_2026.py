import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from learning.models import ExamVersion, Section, ExamNumber, TaskType, Candidate

DATA = Path(__file__).resolve().parents[2] / 'data'
GROUPS = [
 ('geometry','Геометрия','--c3',[1,2,3]),
 ('probability','Вероятность и статистика','--c2',[4,5]),
 ('algebra','Алгебра','--c1',[6,7]),
 ('analysis','Функции и анализ','--c4',[8,11,12]),
 ('applied','Практические задачи','--lavender',[9,10]),
]
TITLES = ['Планиметрия','Векторы','Стереометрия','Начала теории вероятностей','Вероятности сложных событий','Простейшие уравнения','Вычисления и преобразования','Производная и первообразная','Задачи с прикладным содержанием','Текстовые задачи','Графики функций','Наибольшее и наименьшее значение функций']

class Command(BaseCommand):
    help = 'Добавить каталог ЕГЭ-2026 без изменения прогресса и удаления существующих данных.'
    def add_arguments(self, parser):
        parser.add_argument("--catalog-only", action="store_true", help="Создать типы без предварительного реестра кандидатов")

    @transaction.atomic
    def handle(self, *args, **options):
        exam, _ = ExamVersion.objects.update_or_create(code='ege_profile_2026', defaults={'title':'ЕГЭ-2026 · Математика, профиль'})
        numbers = {}
        for pos,(slug,title,accent,ns) in enumerate(GROUPS):
            section,_ = Section.objects.update_or_create(exam=exam,slug=slug,defaults={'title':title,'accent':accent,'position':pos})
            for n in ns:
                numbers[n],_ = ExamNumber.objects.update_or_create(exam=exam,number=n,defaults={'section':section,'title':TITLES[n-1]})
        for row in json.loads((DATA/'types_2026.json').read_text()):
            existing = TaskType.objects.filter(type_id=row['type_id']).first()
            if existing and existing.number.exam_id != exam.pk:
                raise ValueError('type_id уже занят другой версией экзамена')
            slug = existing.slug if existing else f"ege26-{row['type_id'].replace('.', '-')}"
            TaskType.objects.update_or_create(slug=slug,defaults={'type_id':row['type_id'],'number':numbers[row['number']], 'title':row['title'], 'position':int(row['type_id'].split('.')[1]), 'illustration_policy':row['illustration_policy'], 'illustration_required':row['illustration_required']})
        for row in ([] if options['catalog_only'] else json.loads((DATA/'candidates_2026.json').read_text())):
            type_id = row.pop('type_id',None)
            Candidate.objects.get_or_create(source_url=row['source_url'],source_task_id=row['source_task_id'],defaults={**row,'task_type':TaskType.objects.get(type_id=type_id) if type_id else None})
        self.stdout.write(self.style.SUCCESS('56 типов сохранены. Прогресс не изменён.'))
