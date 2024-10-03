""""Authentication."""
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication as BaseTokenAuthentication, get_authorization_header
from ninetofiver import models


class ApiKeyAuthentication(BaseTokenAuthentication):
    """API key authentication."""

    model = models.ApiKey

    def authenticate(self, request): 
        
        # removed the following to prevent the use of query parameters for api_key
        # token = request.GET.get('api_key', None) 

        """Authenticate the request.""" 
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            msg = _('Invalid token header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)

        if len(auth) == 1:
            msg = _('Invalid token header. No credentials provided.')
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = _('Invalid token header. Token string should not contain spaces.')
            raise exceptions.AuthenticationFailed(msg)

        try:
            token = auth[1].decode()
        except UnicodeError:
            msg = _('Invalid token header. Token string should not contain invalid characters.')
            raise exceptions.AuthenticationFailed(msg)

        res = self.authenticate_credentials(token)

        # Only allow GETs using read-only API keys
        if res[1].read_only and (request.method != 'GET'):
            msg = _('The token provided is only valid for read-only requests.')
            raise exceptions.AuthenticationFailed(msg)

        return res
