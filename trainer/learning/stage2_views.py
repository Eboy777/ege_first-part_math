import hashlib
from django.conf import settings
from datetime import timedelta
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import F
from django.http import JsonResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from .models import ExamVersion, ExamNumber, TaskType, Progress, LoginFailure

WINDOW = timedelta(minutes=15)

def throttle_keys(request, username):
    return [(hashlib.sha256(('account:' + username.casefold()).encode()).hexdigest(), 5), (hashlib.sha256(('ip:' + request.META.get('REMOTE_ADDR', '')).encode()).hexdigest(), 30)]

def throttled(keys):
    return any(LoginFailure.objects.filter(key=k, count__gte=limit, window_start__gt=timezone.now()-WINDOW).exists() for k, limit in keys)

def record_failures(keys):
    now = timezone.now()
    for key, _ in keys:
        LoginFailure.objects.get_or_create(key=key, defaults={'window_start': now})
        LoginFailure.objects.filter(key=key, window_start__lte=now-WINDOW).update(count=0, window_start=now)
        LoginFailure.objects.filter(key=key).update(count=F('count')+1)

@login_not_required
def login_page(request):
    if request.method not in ['GET', 'POST']:
        return HttpResponseNotAllowed(['GET', 'POST'])
    if request.user.is_authenticated:
        return redirect('home')
    form = AuthenticationForm(request, data=request.POST if request.method=='POST' else None)
    status = 200
    rate_error = None
    if request.method == 'POST':
        keys = throttle_keys(request, request.POST.get('username', '')[:150])
        if throttled(keys):
            rate_error = 'Слишком много попыток входа. Попробуй через 15 минут.'
            status = 429
        elif form.is_valid():
            login(request, form.get_user())
            LoginFailure.objects.filter(key=keys[0][0]).delete()
            target = request.POST.get('next', '')
            return redirect(target if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()) else 'home')
        else:
            record_failures(keys)
            status = 400
    return render(request, 'learning_stage2/login.html', {'form': form, 'next': request.GET.get('next', ''), 'rate_error': rate_error}, status=status)

@require_POST
def logout_page(request):
    from .models import PushSubscription
    endpoint=request.session.get('push_endpoint')
    if endpoint:PushSubscription.objects.filter(user=request.user,endpoint=endpoint).delete()
    logout(request)
    return redirect('login')

def progress_for(user, types):
    # Never accept a student identifier from the browser.
    from .reviews import due_reviews
    due={r.run.task_type_id:r for r in due_reviews(user)}
    values = {p.task_type_id:p for p in Progress.objects.filter(user=user, task_type__in=types)}
    rows = []
    for t in types:
        p = values.get(t.pk)
        completed = p.completed if p else 0
        rows.append({'review':due.get(t.pk),'type': t, 'completed': completed, 'is_demo': bool(p and p.is_demo), 'segments': [{'done': i<completed, 'control': i>=3} for i in range(5)]})
    return rows

@require_GET
def home(request):
    exam = ExamVersion.objects.filter(code=settings.TRAINER_EXAM_VERSION).first()
    groups = []
    if exam:
        for section in exam.sections.prefetch_related('numbers__types'):
            cards = []
            for n in section.numbers.all():
                rows = progress_for(request.user, list(n.types.all()))
                count = sum(r['completed']==5 for r in rows)
                cards.append({'due':sum(bool(r['review']) for r in rows),'number':n,'mastered':count,'total':len(rows),'percent':round(100*count/len(rows)) if rows else 0})
            groups.append({'section':section,'cards':cards})
    return render(request, 'learning_stage2/home.html', {'exam':exam, 'groups':groups})

@require_GET
def number_page(request, version, number):
    n = get_object_or_404(ExamNumber.objects.select_related('exam'), exam_id=version, number=number)
    rows=progress_for(request.user,list(n.types.all()))
    only_due=request.GET.get('review')=='due'
    if only_due:rows=[r for r in rows if r['review']]
    return render(request, 'learning_stage2/number.html', {'exam':n.exam,'number':n,'rows':rows,'only_due':only_due})

@require_GET
def type_page(request, version, slug):
    t = get_object_or_404(TaskType.objects.select_related('number__exam'), pk=slug, number__exam_id=version)
    return render(request, 'learning_stage2/type.html', {'exam':t.number.exam, 'row':progress_for(request.user,[t])[0]})

@require_GET
def mistakes_page(request):
    return render(request, 'learning_stage2/mistakes.html')

@require_GET
def api_me(request):
    return JsonResponse({'id':request.user.pk,'login':request.user.username,'name':request.user.first_name or request.user.username})

@require_GET
def api_progress(request, progress_id=None):
    if request.GET:
        return JsonResponse({'error':'unsupported_parameters'},status=400)
    rows = Progress.objects.filter(user=request.user).select_related('task_type')
    if progress_id is not None:
        p = get_object_or_404(rows,pk=progress_id)
        return JsonResponse({'id':str(p.pk),'type_id':p.task_type_id,'completed':p.completed,'is_demo':p.is_demo})
    return JsonResponse({'progress':[{'id':str(p.pk),'type_id':p.task_type_id,'completed':p.completed,'is_demo':p.is_demo} for p in rows]})

