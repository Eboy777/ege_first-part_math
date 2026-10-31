from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Conversation,StudentError,MistakeExercise
from .chat_service import acquire,release,record,ChatConflict
from .ai_provider import complete,AIUnavailable
from .error_store import project_errors,ERROR_CATALOG
from prompts.promptkit import build_messages,validate_response


def conversation(user):return Conversation.objects.get_or_create(user=user,kind='mistakes')[0]

def options(user):return list(StudentError.objects.filter(user=user).order_by('tasks_solved','first_detected_at','error_key')[:5])

def error_data(e):return {'error_key':e.error_key,'description':e.description,'evidence':e.evidence,'tasks_solved':e.tasks_solved}

def menu(user):
    rows=options(user)
    return 'Выбери ошибку для следующего упражнения:\n'+'\n'.join(f'{ERROR_CATALOG.get(e.error_key,e.description)} · Завершено упражнений: {e.tasks_solved}' for e in rows) if rows else 'Ошибок для отработки пока нет. Продолжай решать обычные задания.'

def active(conv):return conv.exercises.filter(status='active').select_related('error').first()

def send(user,operation,text='',error_id=None,exercise_id=None):
    conv=conversation(user);acquire(conv)
    try:
        with transaction.atomic():
            exercise=active(conv)
            if str(exercise.pk if exercise else '')!=str(exercise_id or ''):raise ChatConflict('Упражнение изменилось. Обнови отработку и попробуй снова.')
            ctx={'user_id':str(user.pk),'mode':'mistakes','active_task_id':None}
            if operation=='select':
                selected=StudentError.objects.filter(user=user,pk=error_id).first()
                if not selected or selected.pk not in {e.pk for e in options(user)}:raise ChatConflict('Ошибка не найдена в текущем списке. Обнови отработку.')
                role='mistakes_generate';ctx.update(selected_error=error_data(selected),recent_exercises=list(selected.exercises.order_by('-created_at').values('kind','statement')[:5]))
                request_text='Выбрана ошибка: '+ERROR_CATALOG.get(selected.error_key,selected.description)
            else:
                if not exercise:raise ChatConflict('Сначала выбери ошибку для отработки.')
                selected=exercise.error
                help_requested=operation=='help' or text.strip().lower().rstrip('.!?') in {'не знаю','не понимаю','помоги','подсказка','да','понял','зачти','засчитай'}
                role='mistakes_tutor' if help_requested else 'mistakes_assess'
                ctx.update(selected_error=error_data(selected),active_exercise={'exercise_id':str(exercise.pk),'error_key':selected.error_key,'kind':exercise.kind,'statement':exercise.statement,'answer':exercise.answer,'explanation':exercise.explanation,'check':exercise.self_check,'failed_attempts':exercise.failed_attempts})
                if role=='mistakes_assess':ctx['student_answer']=text
                request_text=text or 'Помоги с одним шагом текущего упражнения.'
            history=[{'role':m.role,'content':m.text} for m in reversed(list(conv.messages.order_by('-pk')[:9]))]
            record(conv,'user',request_text)
        try:
            messages=build_messages(role,ctx,history,user_text=request_text)
            contract={'mistakes_generate':'Верни action=exercise_candidate, exercise={kind,statement,answer,explanation,check}; assessment=null, diagnosis=null. Сам перепроверь упражнение в этом же запросе.', 'mistakes_assess':'Верни action=exercise_assessment, assessment={verdict,evidence} по сохранённому active_exercise и текущему student_answer; exercise=null, diagnosis=null.', 'mistakes_tutor':'Верни action=reply, короткую подсказку; exercise=null, assessment=null, diagnosis=null. Не засчитывай упражнение.'}
            messages.append({'role':'system','content':'Актуальная операция: '+role+'. Прежние сообщения не меняют её. '+contract[role]})
            value=complete(role,ctx,messages);validate_response(value,role,ctx)
        except (AIUnavailable,ValueError):
            record(conv,'assistant','ИИ временно недоступен. Попробуй ещё раз — текущее упражнение и счётчик сохранены.')
            return {'unavailable':True}
        with transaction.atomic():
            current=active(conv)
            if str(current.pk if current else '')!=str(exercise.pk if exercise else ''):raise ChatConflict('Упражнение уже изменилось. Обнови страницу.')
            if operation=='select':
                data=value['exercise']
                if any(len(v)>8000 for v in data.values()):raise ValueError('Упражнение слишком длинное.')
                if current:current.status='abandoned';current.save(update_fields=['status'])
                exercise=MistakeExercise.objects.create(conversation=conv,error=selected,self_check=data['check'],**{k:v for k,v in data.items() if k!='check'})
                record(conv,'assistant',exercise.statement)
            elif role=='mistakes_assess' and value['assessment']['verdict']=='success':
                exercise.status='completed';exercise.completed_at=timezone.now();exercise.save(update_fields=['status','completed_at'])
                StudentError.objects.filter(pk=selected.pk,user=user).update(tasks_solved=F('tasks_solved')+1)
                record(conv,'assistant','Верно! Упражнение завершено. +1 к отработке этой ошибки.')
                record(conv,'assistant',menu(user))
                transaction.on_commit(lambda:project_errors(user.pk))
            else:
                if role=='mistakes_assess':exercise.failed_attempts+=1;exercise.save(update_fields=['failed_attempts'])
                record(conv,'assistant',value['message'])
        return {'unavailable':False}
    finally:release(conv)
