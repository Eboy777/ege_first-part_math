"""Review dates and credits are exclusively server-owned."""
from datetime import timedelta
from django.utils import timezone
from .models import Review, Attempt, AnswerSubmission
from .answers import normalize_answer, answer_matches


def schedule(run):
    if run.completed!=5 or not run.mastered_at:return []
    seven,_=Review.objects.get_or_create(run=run,interval=7,defaults={'due_at':run.mastered_at+timedelta(days=7)})
    thirty,_=Review.objects.get_or_create(run=run,interval=30,defaults={'due_at':seven.completed_at+timedelta(days=30) if seven.completed_at else None})
    ninety,_=Review.objects.get_or_create(run=run,interval=90,defaults={'due_at':run.mastered_at+timedelta(days=90)})
    return [seven,thirty,ninety]


def next_review(run):
    return run.reviews.filter(completed_at__isnull=True).order_by('interval').first()


def active_review(run):
    return run.reviews.filter(started_at__isnull=False,completed_at__isnull=True).order_by('interval').first()


def review_current(review):
    return review.attempts.exclude(status='replaced').order_by('-stage','-pk').first()


def issue(review):
    from .training import available
    task=available(review.run).first()
    if not task:return None
    return Attempt.objects.create(run=review.run,review=review,task=task,stage=4+review.completed)


def act_review(run,action,attempt_id,answer):
    # Called inside the training engine's IMMEDIATE transaction and run lock.
    schedule(run)
    review=active_review(run)
    if action=='start_review':
        if review:return ''
        review=next_review(run)
        if not review or not review.due_at or review.due_at>timezone.now():return 'Срок повторения ещё не наступил.'
        attempt=issue(review)
        if not attempt:return 'Подходящие проверенные задачи закончились. Прогресс сохранён.'
        review.started_at=timezone.now();review.save(update_fields=['started_at'])
        return ''
    if not review:return 'Выбери наступившее повторение.'
    attempt=review_current(review)
    if not attempt or str(attempt.pk)!=str(attempt_id):return 'Эта попытка уже не текущая. Страница обновлена.'
    if action=='theory':
        if attempt.status!='solved':attempt.assisted=True;attempt.save(update_fields=['assisted'])
        return ''
    if action=='next':
        if not(attempt.status=='solved' or attempt.assisted):return 'Сначала заверши текущую задачу.'
        if not issue(review):return 'Подходящие проверенные задачи закончились. Прогресс сохранён.'
        attempt.status='replaced';attempt.save(update_fields=['status']);return ''
    if action=='answer':
        if attempt.status=='solved':return 'Ответ уже обработан.'
        if normalize_answer(answer) is None:return 'Введи корректное число. Подойдут точка и запятая.'
        correct=answer_matches(attempt.task,answer)
        AnswerSubmission.objects.create(attempt=attempt,answer=answer.strip(),correct=correct)
        if not correct:
            attempt.status='incorrect';attempt.save(update_fields=['status']);return 'Ответ неверный. Попробуй исправить решение.'
        attempt.status='solved'
        if not attempt.assisted:
            attempt.credited_at=timezone.now();review.completed+=1
            if review.completed==2:
                review.completed_at=timezone.now()
                if review.interval==7:run.reviews.filter(interval=30).update(due_at=review.completed_at+timedelta(days=30))
            review.save()
        attempt.save()
        return 'Повторение завершено · 2/2. Освоение типа сохранено: 5/5.' if review.completed_at else ''
    return 'Неизвестное действие.'


def due_reviews(user):
    # One earliest outstanding checkpoint per type; overdue checkpoints never disappear.
    rows=Review.objects.filter(run__user=user,run__completed=5,run__mastered_at__isnull=False,completed_at__isnull=True).select_related('run__task_type__number').order_by('run_id','interval')
    seen=set();result=[];now=timezone.now()
    for r in rows:
        if r.run_id in seen:continue
        seen.add(r.run_id)
        if r.due_at and r.due_at<=now:result.append(r)
    return result
