from django.test import SimpleTestCase,RequestFactory
from .middleware import ProxyClientAddressMiddleware

class ProxyAddressTests(SimpleTestCase):
    def test_only_local_proxy_can_supply_real_address(self):
        middleware=ProxyClientAddressMiddleware(lambda request:request.META['REMOTE_ADDR'])
        factory=RequestFactory()
        self.assertEqual(middleware(factory.get('/',REMOTE_ADDR='127.0.0.1',HTTP_X_REAL_IP='203.0.113.8')),'203.0.113.8')
        self.assertEqual(middleware(factory.get('/',REMOTE_ADDR='198.51.100.7',HTTP_X_REAL_IP='203.0.113.8')),'198.51.100.7')
        self.assertEqual(middleware(factory.get('/',REMOTE_ADDR='127.0.0.1',HTTP_X_REAL_IP='invalid')),'127.0.0.1')
