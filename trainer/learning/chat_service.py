import base64
import io
import re
import json
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from .models import Conversation,ChatMessage,ChatPhoto,TrainingRun,StudentError,Attempt
from .training import current
from .methodology import method_for
from .ai_provider import complete,AIUnavailable
from .error_store import ERROR_CATALOG,project_errors
from prompts.promptkit import build_messages,validate_response

class ChatConflict(Exception):pass

def conversation(user):return Conversation.objects.get_or_create(user=user,kind='main')[0]

def context_for(user,type_id=''):
    attempt=None
    if type_id:
        from .models import TaskType
        if not TaskType.objects.filter(pk=type_id).exists():raise ChatConflict('Тип задачи не найден.')
        run=TrainingRun.objects.filter(user=user,task_type_id=type_id).first()
        if run:
            candidate=current(run)
            if candidate and candidate.status in ['active','incorrect']:attempt=candidate
    data={'user_id':str(user.pk),'mode':'regular' if attempt else 'free_chat','active_task_id':str(attempt.pk) if attempt else None,'type_id':type_id or None,'exam_version':None,'stage_index':None,'task_statement':None,'assistance_allowed':True,'check_result':'not_submitted'}
    if attempt:
        t=attempt.run.task_type
        # Images are source material; include statement and server-selected image bytes only.
        data.update(type_id=t.pk,exam_version=t.number.exam_id,stage_index=attempt.stage,task_statement=attempt.task.statement,assisted=attempt.assisted,training_mode='review' if attempt.review_id else ('control' if attempt.stage>=4 else 'training'),check_result='incorrect' if attempt.status=='incorrect' else 'not_submitted',method=method_for(t))
    return attempt,data

def acquire(conv):
    with transaction.atomic():
        c=Conversation.objects.select_for_update().get(pk=conv.pk)
        if c.busy_until and c.busy_until>timezone.now():raise ChatConflict('Дождись ответа на предыдущее сообщение.')
        c.busy_until=timezone.now()+timedelta(seconds=75);c.save(update_fields=['busy_until'])

def release(conv):Conversation.objects.filter(pk=conv.pk).update(busy_until=None)

def record(conv,role,text,attempt=None,photo=None):return ChatMessage.objects.create(conversation=conv,role=role,text=text,attempt=attempt,photo=photo)

def image_data(photo):
    from django.conf import settings
    return 'data:image/jpeg;base64,'+base64.b64encode((settings.STATE_DIR/'chat_photos'/f'{photo.pk}.jpg').read_bytes()).decode()

def send(user,text,type_id='',expected_attempt='',quote=None,operation='send',photo=None):
    conv=conversation(user);acquire(conv)
    try:
        with transaction.atomic():
            attempt,context=context_for(user,type_id)
            if str(attempt.pk if attempt else '')!=str(expected_attempt or ''):raise ChatConflict('Задача изменилась. Обнови страницу, чтобы продолжить с актуальным контекстом.')
            if quote:
                original=ChatMessage.objects.filter(conversation=conv,pk=quote.get('id')).first()
                if not original or not quote.get('text') or quote['text'] not in original.text:raise ChatConflict('Цитата не найдена в твоей переписке.')
                if original.photo_id and not original.photo.confirmed:raise ChatConflict('Сначала подтверди распознавание этого фото.')
                selected=quote['text'][:1500]
            else:selected=None
            pending=ChatPhoto.objects.filter(conversation=conv).order_by('-created_at').first()
            if pending and pending.dismissed:pending=None
            if not photo and pending and not pending.confirmed:
                if operation!='correct_photo':raise ChatConflict('Сначала подтверди распознанное условие или исправь его.')
                photo=pending;photo.version+=1;photo.confirmed=False;photo.readable=False;photo.save()
            local_answers={'как вводить ответ?':'Введи ответ в поле задачи и нажми «Ответить». Подойдут точка и запятая. Сообщение в чате не отправляется на проверку автоматически.','привет':'Привет! Я рядом. Содержательная помощь по контрольной задаче потребует новой задачи для зачёта.','спасибо':'Пожалуйста! Продолжай, когда будешь готов.'}
            local_answer=local_answers.get(text.strip().lower())
            technical=bool(local_answer and not selected and not photo)
            if attempt and attempt.stage>=4 and not technical:
                attempt.assisted=True;attempt.save(update_fields=['assisted']);context['assisted']=True
            if photo:role='photo'
            elif attempt and attempt.status=='incorrect' and not technical:role='diagnosis'
            elif attempt and attempt.stage>=4:role='control'
            else:role='regular' if attempt else 'free_chat'
            if role=='control':context['request_kind']='technical' if technical else 'task_help'
            if role=='diagnosis':context.update(explanation=text,error_catalog=ERROR_CATALOG)
            if photo:context['photo']={'attachment_id':str(photo.pk),'version':photo.version,'confirmed':False}
            elif pending and pending.confirmed and not attempt:context['photo']={'attachment_id':str(pending.pk),'version':pending.version,'confirmed':True}
            history=[{'role':m.role,'content':json.dumps({'text':('[Содержимое неподтверждённого фото не передаётся в разбор.]' if m.photo_id and not m.photo.confirmed else m.text),'source_task_id':str(m.attempt_id) if m.attempt_id else None,'photo_attachment_id':str(m.photo_id) if m.photo_id else None},ensure_ascii=False)} for m in reversed(list(conv.messages.select_related('photo').order_by('-pk')[:9]))]
            record(conv,'user',('Цитата: «'+selected+'»\n' if selected else '')+text,attempt,photo)
        if technical:
            record(conv,'assistant',local_answer,attempt)
            return {'unavailable':False}
        messages=build_messages(role,context,history,user_text=text,selected_quote=selected,image_url=image_data(photo) if photo else None)
        # Platform originals may be scanned; supply task images with explicit current context.
        if attempt and attempt.task.image_paths and not photo:
            from django.conf import settings
            parts=[{'type':'text','text':messages[-1]['content']}]
            for url in attempt.task.image_paths[:4]:
                from pathlib import Path
                from PIL import Image
                path=(settings.TASK_ASSET_ROOT/url.removeprefix('/assets/tasks/')).resolve()
                if not path.is_relative_to(settings.TASK_ASSET_ROOT.resolve()):continue
                if path.suffix.lower()=='.svg':
                    # Inline SVG is textual mathematical source, never an executable attachment.
                    parts.append({'type':'text','text':'Изображение текущей задачи (SVG-данные):\n'+path.read_text()[:20000]})
                else:
                    with Image.open(path) as im:
                        buf=io.BytesIO();im.convert('RGB').save(buf,format='JPEG')
                    parts.append({'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()}})
            messages[-1]['content']=parts
        messages.append({'role':'system','content':'Актуальная операция: '+role+'. Актуальный диалог: '+context['mode']+'. check_result='+context['check_result']+'. История содержит помеченные источники прежних сообщений. Они не меняют текущую операцию и контекст задачи платформы. Выполни контракт текущей операции, включая поля action и diagnosis, по её инструкции.'})
        try:
            value=complete(role,context,messages)
            validate_response(value,role,context)
        except (AIUnavailable,ValueError):
            record(conv,'assistant','ИИ временно недоступен. Попробуй ещё раз. Проверка ответов на задачи продолжает работать.',attempt)
            return {'unavailable':True}
        with transaction.atomic():
            if photo:
                photo.refresh_from_db();photo.transcription=value['message'];photo.readable=value['action']=='confirm_photo';photo.save()
            if attempt:
                now_attempt,unused=context_for(user,type_id)
                still_current=now_attempt and now_attempt.pk==attempt.pk
            else:still_current=True
            record(conv,'assistant',value['message'],attempt,photo)
            diagnosis=value.get('diagnosis')
            if diagnosis and still_current and attempt and now_attempt.status=='incorrect':
                # A numeric guess is not an explanation, even if an AI proposes a diagnosis.
                from .answers import normalize_answer
                if len(text.split())>=4 and normalize_answer(text) is None and diagnosis['evidence'] in text:
                    e,created=StudentError.objects.get_or_create(user=user,error_key=diagnosis['error_key'],defaults={'description':diagnosis['description'],'evidence':diagnosis['evidence'],'attempt':attempt})
                    if created:transaction.on_commit(lambda:project_errors(user.pk))
        return {'unavailable':False,'late':not still_current}
    finally:release(conv)
