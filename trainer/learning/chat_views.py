import io
import json
import uuid
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse,FileResponse,Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET,require_POST
from .models import ChatPhoto,ChatMessage
from .chat_service import conversation,context_for,send,ChatConflict,record


def serialized(m):return {'id':m.pk,'role':m.role,'text':m.text,'attempt_id':str(m.attempt_id) if m.attempt_id else None,'photo_url':f'/api/chat/photos/{m.photo_id}' if m.photo_id else None}

def snapshot(request):
    conv=conversation(request.user)
    try:before=int(request.GET.get('before','0'))
    except ValueError:before=0
    rows=conv.messages.order_by('-pk')
    if before:rows=rows.filter(pk__lt=before)
    rows=list(rows[:50]);pending=ChatPhoto.objects.filter(conversation=conv).order_by('-created_at').first()
    attempt,context=context_for(request.user,request.GET.get('type',''))
    return {'messages':[serialized(m) for m in reversed(rows)],'has_older':bool(rows and conv.messages.filter(pk__lt=rows[-1].pk).exists()),'context':{'attempt_id':context['active_task_id'],'control':bool(attempt and attempt.stage>=4),'assisted':bool(attempt and attempt.assisted)},'photo':{'id':str(pending.pk),'version':pending.version,'text':pending.transcription,'readable':pending.readable} if pending and not pending.confirmed and not pending.dismissed else None}

@require_GET
def history(request):
    try:return JsonResponse(snapshot(request))
    except ChatConflict as exc:return JsonResponse({'error':str(exc)},status=409)

@require_POST
def message(request):
    try:
        data=json.loads(request.body)
        text=data.get('text','')
        if not isinstance(text,str) or not text.strip() or len(text)>6000:return JsonResponse({'error':'Сообщение должно содержать от 1 до 6000 символов.'},status=400)
        if data.get('quote') and (not isinstance(data['quote'],dict) or len(str(data['quote'].get('text','')))>1500):return JsonResponse({'error':'Слишком длинная цитата.'},status=400)
        result=send(request.user,text.strip(),data.get('type',''),data.get('attempt',''),data.get('quote'),data.get('operation','send'))
        return JsonResponse(result)
    except (ValueError,TypeError,AttributeError):return JsonResponse({'error':'Некорректное сообщение.'},status=400)
    except ChatConflict as exc:return JsonResponse({'error':str(exc)},status=409)

@require_POST
def upload(request):
    from PIL import Image,ImageOps
    f=request.FILES.get('photo')
    if not f or f.size>5*1024*1024:return JsonResponse({'error':'Выбери JPEG, PNG или WebP до 5 МБ.'},status=400)
    try:
        with Image.open(f) as im:
            if im.format not in ['JPEG','PNG','WEBP'] or im.width*im.height>16_000_000:raise ValueError()
            im.load();image=ImageOps.exif_transpose(im).convert('RGB');image.thumbnail((1800,1800));buf=io.BytesIO();image.save(buf,format='JPEG',quality=90)
    except Exception:return JsonResponse({'error':'Не удалось прочитать изображение. Допустимы JPEG, PNG и WebP.'},status=400)
    conv=conversation(request.user)
    # Check context before creating a pending attachment.
    try:
        attempt,context=context_for(request.user,request.POST.get('type',''))
        if str(context['active_task_id'] or '')!=request.POST.get('attempt',''):raise ChatConflict('Задача изменилась. Обнови страницу.')
        if conv.busy_until and conv.busy_until>__import__('django.utils.timezone',fromlist=['now']).now():raise ChatConflict('Дождись ответа на предыдущее сообщение.')
        photo=ChatPhoto.objects.create(conversation=conv)
        root=settings.STATE_DIR/'chat_photos';root.mkdir(mode=0o700,exist_ok=True)
        p=root/f'{photo.pk}.jpg';p.write_bytes(buf.getvalue());p.chmod(0o600)
        result=send(request.user,'Прочитай условие на фото и попроси подтвердить его.',request.POST.get('type',''),request.POST.get('attempt',''),photo=photo)
        return JsonResponse(result)
    except ChatConflict as exc:
        if 'photo' in locals():photo.delete();p.unlink(missing_ok=True)
        return JsonResponse({'error':str(exc)},status=409)

@require_POST
def confirm(request):
    try:data=json.loads(request.body)
    except ValueError:return JsonResponse({'error':'Некорректный запрос.'},status=400)
    try:uuid.UUID(str(data.get('id')));version=int(data.get('version'))
    except (ValueError,TypeError,AttributeError):return JsonResponse({'error':'Некорректное фото или версия.'},status=400)
    with transaction.atomic():
        photo=get_object_or_404(ChatPhoto.objects.select_for_update(),pk=data.get('id'),conversation__user=request.user,conversation__kind='main')
        if photo.dismissed or photo.version!=data.get('version') or not photo.readable or not photo.transcription:return JsonResponse({'error':'Условие изменилось или требует уточнения. Сначала исправь распознавание.'},status=409)
        if not photo.confirmed:
            photo.confirmed=True;photo.save(update_fields=['confirmed']);record(photo.conversation,'user','Подтверждаю распознанное условие.',photo=photo)
    return JsonResponse({'confirmed':True})

@require_GET
def photo_file(request,photo_id):
    photo=get_object_or_404(ChatPhoto,pk=photo_id,conversation__user=request.user)
    p=settings.STATE_DIR/'chat_photos'/f'{photo.pk}.jpg'
    if not p.is_file():raise Http404
    return FileResponse(p.open('rb'),content_type='image/jpeg')

@require_POST
def dismiss_photo(request):
    try:
        data=json.loads(request.body);uuid.UUID(str(data.get('id')))
    except (ValueError,TypeError,AttributeError):return JsonResponse({'error':'Некорректное фото.'},status=400)
    with transaction.atomic():
        photo=get_object_or_404(ChatPhoto.objects.select_for_update(),pk=data['id'],conversation__user=request.user)
        if photo.confirmed or photo.version!=data.get('version'):return JsonResponse({'error':'Состояние фото изменилось.'},status=409)
        photo.dismissed=True;photo.save(update_fields=['dismissed'])
    return JsonResponse({'dismissed':True})
