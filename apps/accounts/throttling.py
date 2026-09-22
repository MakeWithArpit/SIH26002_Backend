from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """
    Limits authentication attempts on the /login/ endpoint to prevent brute-force attacks.
    Limit: 5 requests per minute per IP address.
    """
    scope = 'login'
    rate = '5/minute'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }


class RegisterRateThrottle(SimpleRateThrottle):
    """
    Limits registration attempts on the /register/ endpoint to prevent automated account creation.
    Limit: 3 requests per minute per IP address.
    """
    scope = 'register'
    rate = '3/minute'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }
