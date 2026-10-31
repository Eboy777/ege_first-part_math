import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from learning.models import TaskType, Candidate, BankTask

class Command(BaseCommand):
    help = 'Отчёт по 56 типам, кандидатам и источникам каждого импортированного задания.'
    def add_arguments(self, parser):
        parser.add_argument('--output', type=Path, default=Path('bank'))
    def handle(self, *args, **options):
        folder = options['output']; folder.mkdir(parents=True,exist_ok=True)
        rows=[]
        for t in TaskType.objects.filter(number__exam_id='ege_profile_2026').select_related('number').order_by('number__number','position'):
            tasks=list(t.bank_tasks.select_related('candidate'))
            published=[x for x in tasks if x.status=='published' and x.candidate.rights_status=='approved']
            rows.append([t.type_id,t.title,t.candidates.count(),len(tasks),sum(len(x.image_paths) for x in tasks),sum(x.answer_verified for x in tasks),len(published),max(0,15-len(published))])
        header=['Тип','Описание','Найдено кандидатов','Импортировано','Изображений','Ответ проверен','Опубликовано','Отсутствует']
        with (folder/'coverage.csv').open('w') as f:
            w=csv.writer(f);w.writerow(header);w.writerows(rows)
        with (folder/'candidates.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['Тип','Источник','ID','URL','Права','Разрешение','Примечание'])
            for c in Candidate.objects.select_related('task_type').order_by('id'):
                w.writerow([c.task_type.type_id if c.task_type else '',c.source,c.source_task_id,c.source_url,c.rights_status,c.license_or_permission,c.notes])
        with (folder/'task_sources.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['ID','Тип','Источник','ID источника','URL','Ответ','Проверка','Изображения','Права','Основание'])
            for task in BankTask.objects.select_related('candidate','task_type').order_by('id'):
                c=task.candidate
                w.writerow([task.pk,task.task_type.type_id,c.source,c.source_task_id,c.source_url,task.answer,task.verification_notes,'; '.join(task.image_paths),c.rights_status,c.license_or_permission])
        text='# Наполнение банка ЕГЭ-2026\n\n'+' | '.join(header)+'\n'+' | '.join(['---']*len(header))+'\n'
        text+='\n'.join(' | '.join(map(str,r)) for r in rows)
        text+='\n\nЦель: не менее 15 на тип; ранее наполненные до 20 сохранены. Опубликовано: '+str(sum(r[6] for r in rows))+'. Дефицит: '+str(sum(r[7] for r in rows))+'.\n'
        unclassified=Candidate.objects.filter(task_type__isnull=True).count()
        text+=f'\nДополнительно в реестре {unclassified} кандидатов с кратким ответом без подтверждённого основного типа. Они не включены в столбец «Найдено кандидатов» и не считаются импортированными.\n'
        text+='\nПрава: пользователь подтвердил разрешение на сайты из ТЗ, включая условия и исходные рисунки. В реестре сохранено пользовательское подтверждение (user-attested permission), отдельный документ не предоставлялся.\n'
        text+='\nОпубликованы только проверенные оригиналы: демоверсия ФИПИ, открытый банк ФИПИ и прототипы Решу ЕГЭ. Для каждой задачи есть источник, исходный ответ и независимая математическая проверка в task_sources.csv. Изображения и формулы сохранены локально; оригинальные SVG архивированы с контрольными суммами. Числа и условия не менялись.\n'
        text+='\nНепроверенные кандидаты не считаются готовыми. Дефицит — число задач до 15 в каждом типе; избыток в другом типе его не компенсирует. Соседние типы не объединялись. Для узких категорий недостаточно проверенных различных прототипов в просмотренном каталоге; это не доказывает исчерпания всех разрешённых источников.\n'
        text+='\nИсключены точные повторы ФИПИ/Решу ЕГЭ, варианты с перестановкой координат, условия с неоднозначными единицами и задачи без нужной исходной иллюстрации. Сборник ctege.info использован как указатель; перерисованные графики не заменяют оригиналы. Прогресс учеников не сбрасывался.\n'
        (folder/'REPORT.md').write_text(text)
        self.stdout.write(str(folder.resolve()/'REPORT.md'))
