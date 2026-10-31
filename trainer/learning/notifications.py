"""Small Web Push adapter. No mail, external scheduler or service account."""
import base64
import fcntl
import json
import os
from urllib.parse import urlsplit
from django.conf import settings
from .models import PushSubscription
from .reviews import due_reviews


def valid_endpoint(endpoint):
    try:
        u=urlsplit(endpoint)
        return (len(endpoint)<=2048 and u.scheme=='https' and not u.username and not u.password and u.port in (None,443) and not u.fragment and bool(u.path) and (u.hostname in {'fcm.googleapis.com','updates.push.services.mozilla.com','push.services.mozilla.com','web.push.apple.com'} or u.hostname.endswith('.push.apple.com')))
    except (ValueError,AttributeError,TypeError):return False


def vapid():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    root=settings.STATE_DIR
    with (root/'vapid.lock').open('a') as lock:
        os.chmod(root/'vapid.lock',0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        path=root/'vapid.pem'
        if not path.exists():
            key=ec.generate_private_key(ec.SECP256R1())
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        key=serialization.load_pem_private_key(path.read_bytes(),password=None)
    public=key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    return str(path),base64.urlsafe_b64encode(public).decode().rstrip('=')


def send_due_notifications():
    from pywebpush import webpush,WebPushException
    path,_=vapid();sent=0
    # Serialize local senders; no network request holds a SQLite transaction.
    with (settings.STATE_DIR/'push-sender.lock').open('a') as lock:
        os.chmod(settings.STATE_DIR/'push-sender.lock',0o600);fcntl.flock(lock,fcntl.LOCK_EX)
        for sub in PushSubscription.objects.select_related('user').filter(user__is_active=True):
            if not valid_endpoint(sub.endpoint):continue
            due=due_reviews(sub.user);ids=[r.pk for r in due]
            if not any(i not in sub.notified_reviews for i in ids):continue
            try:
                webpush(subscription_info={'endpoint':sub.endpoint,'keys':sub.keys},data=json.dumps({'title':'Пятёрка · пора повторить','body':f'Типов для повторения: {len(due)}. Закрепим знания?','url':'/','tag':'pyaterka-reviews'},ensure_ascii=False),vapid_private_key=path,vapid_claims={'sub':os.environ.get('TRAINER_PUBLIC_ORIGIN','https://localhost')},ttl=3600,timeout=10)
            except WebPushException as exc:
                response=getattr(exc,'response',None)
                if response is not None and response.status_code in (404,410):sub.delete()
                continue
            except Exception:continue
            sub.notified_reviews=list(set(sub.notified_reviews+ids));sub.save(update_fields=['notified_reviews']);sent+=1
    return sent
