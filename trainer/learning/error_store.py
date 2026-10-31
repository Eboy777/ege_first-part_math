"""Database deduplication; private atomic JSON projection, never sent to main AI."""
import fcntl
import json
import os
import tempfile
from django.conf import settings
from .models import StudentError

ERROR_CATALOG={
 'pythagoras:sum_lengths':'Сложение длин катетов вместо квадратов',
 'pythagoras:missing_root':'Не извлечён корень из суммы квадратов',
 'arithmetic:sign':'Ошибка знака при вычислении',
 'quadratic:discriminant_sign':'Ошибка знака в дискриминанте',
 'powers:addition':'Неверное применение свойств степеней',
 'sqrt:square_modulus':'Пропущен модуль при извлечении корня из квадрата',
 'probability:complement':'Перепутаны событие и противоположное событие',
 'geometry:height_side':'Сторона принята за высоту',
 'derivative:chain_rule':'Пропущен множитель внутренней производной',
 'logarithm:domain':'Не учтена область определения логарифма',
 'function:value_coordinate':'Перепутаны значение функции и координата точки',
 'fractions:addition':'Неправильное сложение дробей',
}

def project_errors(user_id):
    root=settings.STATE_DIR/'student_errors';root.mkdir(mode=0o700,exist_ok=True)
    lock=root/f'{user_id}.lock'
    fd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600)
    with os.fdopen(fd,'a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        rows=StudentError.objects.filter(user_id=user_id).order_by('first_detected_at','pk')
        data={'user_id':user_id,'errors':[{'error_key':e.error_key,'title':ERROR_CATALOG.get(e.error_key,e.description),'description':e.description,'related_type_ids':[e.attempt.run.task_type_id],'tasks_solved':e.tasks_solved,'first_detected_at':e.first_detected_at.isoformat()} for e in rows.select_related('attempt__run')]}
        tmp_fd,name=tempfile.mkstemp(dir=root)
        try:
            with os.fdopen(tmp_fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2)
            os.replace(name,root/f'{user_id}.json')
        finally:
            if os.path.exists(name):os.unlink(name)
