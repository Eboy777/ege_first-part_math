import json
import uuid
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET,require_POST
from . import mistakes_service as service
from .chat_service import ChatConflict,record
from .error_store import ERROR_CATALOG

@require_GET
def page(request):return render(request,'learning_stage2/mistakes.html')

@require_GET
def history(request):
    conv=service.conversation(request.user)
    if not conv.messages.exists():record(conv,'assistant',service.menu(request.user))
    try:before=int(request.GET.get('before','0'))
    except ValueError:before=0
    rows=conv.messages.order_by('-pk')
    if before:rows=rows.filter(pk__lt=before)
    rows=list(rows[:50]);exercise=service.active(conv)
    return JsonResponse({'messages':[{'id':m.pk,'role':m.role,'text':m.text} for m in reversed(rows)],'has_older':bool(rows and conv.messages.filter(pk__lt=rows[-1].pk).exists()),'options':[{'id':e.pk,'title':ERROR_CATALOG.get(e.error_key,e.description),'count':e.tasks_solved} for e in service.options(request.user)],'active':{'id':str(exercise.pk),'error_id':exercise.error_id,'title':ERROR_CATALOG.get(exercise.error.error_key,exercise.error.description),'kind':exercise.kind,'statement':exercise.statement} if exercise else None})

@require_POST
def message(request):
    try:
        data=json.loads(request.body);operation=data.get('operation','answer');text=data.get('text','');exercise_id=data.get('exercise_id')
        if operation not in {'select','answer','help'} or not isinstance(text,str) or len(text)>6000:raise ValueError()
        if operation=='answer' and not text.strip():raise ValueError()
        if exercise_id:uuid.UUID(str(exercise_id))
        error_id=int(data['error_id']) if operation=='select' else None
        return JsonResponse(service.send(request.user,operation,text.strip(),error_id,exercise_id))
    except ChatConflict as exc:return JsonResponse({'error':str(exc)},status=409)
    except (ValueError,TypeError,KeyError,AttributeError):return JsonResponse({'error':'Не удалось обработать запрос. Обнови отработку и попробуй снова.'},status=400)
