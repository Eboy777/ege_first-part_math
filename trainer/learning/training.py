from django.db import transaction
from django.utils import timezone
from .models import TrainingRun, Attempt, Progress, BankTask, AnswerSubmission
from .answers import normalize_answer, answer_matches
from .models import Conversation, ChatMessage

def available(run):
    return BankTask.objects.filter(task_type=run.task_type,status='published',answer_verified=True,candidate__rights_status='approved').exclude(pk__in=run.attempts.values('task_id')).order_by('pk')

def current(run):
    from .reviews import active_review,review_current
    review=active_review(run) if run.completed==5 else None
    if review:return review_current(review)
    return run.attempts.filter(review__isnull=True).exclude(status='replaced').order_by('-stage','-pk').first()

def issue(run):
    if run.completed>=5:return None
    task=available(run).first()
    if not task:return None
    return Attempt.objects.create(run=run,task=task,stage=run.completed+1)

@transaction.atomic
def act(user,task_type,action,attempt_id=None,answer=''):
    run,created=TrainingRun.objects.get_or_create(user=user,task_type=task_type)
    if created:
        Progress.objects.filter(user=user,task_type=task_type,is_demo=True).update(completed=0,is_demo=False)
    run=TrainingRun.objects.select_for_update().get(pk=run.pk)
    if run.completed==5 and action!='start':
        from .reviews import act_review
        return act_review(run,action,attempt_id,answer)
    attempt=current(run)
    if action=='start':
        if not attempt and run.completed<5:attempt=issue(run)
        return '' if attempt or run.completed==5 else 'Подходящие проверенные задачи закончились. Прогресс сохранён.'
    if not attempt or str(attempt.pk)!=str(attempt_id):return 'Эта попытка уже не текущая. Страница обновлена.'
    if action=='theory':
        if attempt.stage>=4 and attempt.status!='solved':
            attempt.assisted=True;attempt.save(update_fields=['assisted'])
        return ''
    if action=='next':
        if not (attempt.status=='solved' or attempt.assisted):return 'Сначала заверши текущую задачу.'
        if run.completed>=5:return ''
        if not available(run).exists():return 'Подходящие проверенные задачи закончились. Прогресс сохранён.'
        attempt.status='replaced';attempt.save(update_fields=['status']);issue(run)
        return ''
    if action=='answer':
        if attempt.status=='solved':return 'Ответ уже обработан.'
        if normalize_answer(answer) is None:return 'Введи корректное число. Подойдут точка и запятая.'
        correct=answer_matches(attempt.task,answer)
        AnswerSubmission.objects.create(attempt=attempt,answer=answer.strip(),correct=correct)
        if not correct:
            attempt.status='incorrect';attempt.save(update_fields=['status'])
            if attempt.stage<4:
                conv,_=Conversation.objects.get_or_create(user=user,kind='main')
                ChatMessage.objects.create(conversation=conv,role='assistant',text='Объясни, как ты решал. Какую формулу использовал и что получилось?',attempt=attempt)
            return 'Ответ неверный. Попробуй исправить решение.'
        attempt.status='solved'
        if not(attempt.stage>=4 and attempt.assisted):
            attempt.credited_at=timezone.now();run.completed+=1
            if run.completed==5:run.mastered_at=timezone.now()
            run.save()
            if run.completed==5:
                from .reviews import schedule
                schedule(run)
            Progress.objects.update_or_create(user=user,task_type=task_type,defaults={'completed':run.completed,'is_demo':False})
        attempt.save()
        return ''
    return 'Неизвестное действие.'
