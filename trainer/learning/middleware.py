from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.http import JsonResponse

class ProtectedPagesMiddleware(LoginRequiredMiddleware):
    def handle_no_permission(self, request, view_func):
        if request.path.startswith('/api/'):
            return JsonResponse({'error': 'authentication_required'}, status=401)
        return super().handle_no_permission(request, view_func)

class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith('/static/'):
            response['Cache-Control'] = 'no-store, private'
        response['Referrer-Policy'] = 'same-origin'
        return response

class ProxyClientAddressMiddleware:
    """nginx overwrites X-Real-IP; the app listens only on loopback."""
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        if request.META.get('REMOTE_ADDR') in {'127.0.0.1','::1'}:
            import ipaddress
            try:request.META['REMOTE_ADDR']=str(ipaddress.ip_address(request.META.get('HTTP_X_REAL_IP','')))
            except ValueError:pass
        return self.get_response(request)
