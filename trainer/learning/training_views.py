from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404,render,redirect
from django.views.decorators.http import require_http_methods,require_GET
from .models import TaskType, TrainingRun, Attempt
from .training import act,current
from .stage2_views import progress_for

@require_http_methods(['GET','POST'])
def type_page(request,version,slug):
    if version=='2026' and slug=='right-triangle' and TaskType.objects.filter(pk='ege26-1-1').exists():
        return redirect('type',version='ege_profile_2026',slug='ege26-1-1')
    t=get_object_or_404(TaskType.objects.select_related('number__exam'),pk=slug,number__exam_id=version)
    if request.method=='POST':
        message=act(request.user,t,request.POST.get('action'),request.POST.get('attempt'),request.POST.get('answer',''))
        request.session['training_notice']=message
        request.session['show_theory']=request.POST.get('attempt','') if request.POST.get('action')=='theory' and not message else ''
        return redirect('type',version=version,slug=slug)
    run=TrainingRun.objects.filter(user=request.user,task_type=t).first()
    from .reviews import schedule,active_review,next_review
    checkpoints=schedule(run) if run else []
    review=active_review(run) if run else None
    upcoming=next_review(run) if run else None
    attempt=current(run) if run else None
    return render(request,'learning_stage2/type_training.html',{'exam':t.number.exam,'row':progress_for(request.user,[t])[0],'run':run,'attempt':attempt,'review':review,'checkpoints':checkpoints,'upcoming':upcoming,'review_due':bool(upcoming and upcoming.due_at and upcoming.due_at<=__import__('django.utils.timezone',fromlist=['now']).now()),'notice':request.session.pop('training_notice',''),'show_theory':bool(attempt and str(request.session.pop('show_theory',''))==str(attempt.pk) and (attempt.assisted or attempt.stage<4))})

@require_GET
def task_asset(request,task_id,name):
    if not Attempt.objects.filter(run__user=request.user,task_id=task_id).exists():raise Http404
    root=Path(settings.TASK_ASSET_ROOT).resolve()
    path=(root/task_id/name).resolve()
    if not path.is_relative_to(root/task_id) or not path.is_file():raise Http404
    attempt=Attempt.objects.filter(run__user=request.user,task_id=task_id).select_related('task').first()
    if request.path not in attempt.task.image_paths:raise Http404
    return FileResponse(path.open('rb'))
