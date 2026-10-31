import base64
import json
from pathlib import Path
from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse,FileResponse
from django.views.decorators.http import require_GET,require_POST
from .models import PushSubscription
from .notifications import vapid,valid_endpoint

@require_GET
def config(request):
    _,key=vapid()
    return JsonResponse({'public_key':key})

@require_POST
def subscription(request):
    try:
        data=json.loads(request.body)
        endpoint=data['endpoint']
        if not isinstance(endpoint,str) or not valid_endpoint(endpoint):raise ValueError()
        if data.get('unsubscribe'):
            PushSubscription.objects.filter(user=request.user,endpoint=endpoint).delete()
            return JsonResponse({'ok':True})
        keys=data['keys']
        if set(keys)!={'auth','p256dh'}:raise ValueError()
        def decode(value):
            if not isinstance(value,str) or len(value)>200:raise ValueError()
            return base64.urlsafe_b64decode(value+'='*((-len(value))%4))
        public=decode(keys['p256dh']);auth=decode(keys['auth'])
        if len(public)!=65 or public[0]!=4 or len(auth)!=16:raise ValueError()
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),public)
        sub,created=PushSubscription.objects.get_or_create(endpoint=endpoint,defaults={'user':request.user,'keys':keys})
        if not created:
            if sub.user_id!=request.user.pk:sub.notified_reviews=[]
            sub.user=request.user;sub.keys=keys;sub.save()
        request.session['push_endpoint']=endpoint
        return JsonResponse({'ok':True})
    except (ValueError,KeyError,TypeError,AttributeError):return JsonResponse({'error':'Не удалось сохранить разрешение на уведомления.'},status=400)

@login_not_required
@require_GET
def worker(request):
    return FileResponse((Path(__file__).parent/'static/learning_stage2/sw.js').open('rb'),content_type='application/javascript')

@login_not_required
@require_GET
def manifest(request):
    return JsonResponse({'id':'/','name':'Пятёрка — математика ЕГЭ','short_name':'Пятёрка','lang':'ru','start_url':'/','scope':'/','display':'standalone','background_color':'#fff5dc','theme_color':'#fff5dc','icons':[{'src':'/static/learning_stage2/icon-192.png','sizes':'192x192','type':'image/png'},{'src':'/static/learning_stage2/icon-512.png','sizes':'512x512','type':'image/png'}]},content_type='application/manifest+json')
