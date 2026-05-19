import json
import os
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
]

TOKEN_PATH = Path(settings.BASE_DIR) / 'token.json'
CLIENT_SECRETS_PATH = (
    Path(settings.GOOGLE_CLIENT_SECRETS_FILE)
    if settings.GOOGLE_CLIENT_SECRETS_FILE
    else Path(settings.BASE_DIR) / 'client.json'
)

GOOGLE_AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_TOKEN_URI = 'https://oauth2.googleapis.com/token'


class GoogleOAuthNotConfiguredError(Exception):
    """Raised when OAuth client secrets are missing on disk."""


def _client_config_from_env():
    client_id = settings.GOOGLE_CLIENT_ID or os.environ.get('GOOGLE_CLIENT_ID', '')
    client_secret = settings.GOOGLE_CLIENT_SECRET or os.environ.get('GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret:
        return None

    return {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': GOOGLE_AUTH_URI,
            'token_uri': GOOGLE_TOKEN_URI,
            'redirect_uris': [settings.GOOGLE_OAUTH_REDIRECT_URI],
        },
    }


def get_client_config():
    if CLIENT_SECRETS_PATH.is_file():
        return json.loads(CLIENT_SECRETS_PATH.read_text())

    return _client_config_from_env()


def is_oauth_configured():
    config = get_client_config()
    if not config:
        return False

    web = config.get('web') or config.get('installed') or {}
    return bool(web.get('client_id') and web.get('client_secret'))


def _ensure_client_secrets():
    if not is_oauth_configured():
        raise GoogleOAuthNotConfiguredError(
            'Google OAuth is not configured. Add invoiceinator/client.json '
            '(copy from client.json.example) or set GOOGLE_CLIENT_ID and '
            'GOOGLE_CLIENT_SECRET in the environment, then restart Django.'
        )


def _build_flow(state=None, redirect_uri=None):
    _ensure_client_secrets()
    flow = Flow.from_client_config(
        get_client_config(),
        scopes=SCOPES,
        state=state,
    )
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    return flow


def get_redirect_uri(request=None):
    """Fixed redirect URI on the frontend origin (proxied to Django in dev)."""
    return settings.GOOGLE_OAUTH_REDIRECT_URI


def get_authorization_url(request):
    flow = _build_flow(redirect_uri=get_redirect_uri(request))
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    request.session['google_oauth_state'] = state
    request.session['google_oauth_redirect_uri'] = flow.redirect_uri
    return authorization_url


def save_credentials(credentials):
    TOKEN_PATH.write_text(credentials.to_json())


def load_credentials():
    if not TOKEN_PATH.exists():
        return None

    try:
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            save_credentials(credentials)
        return credentials
    except Exception:
        return None


def exchange_authorization_code(request):
    code = request.GET.get('code')
    if not code:
        raise ValueError('Missing authorization code')

    state = request.session.get('google_oauth_state')
    if not state:
        raise ValueError('OAuth state is missing from the session')

    redirect_uri = request.session.get('google_oauth_redirect_uri') or get_redirect_uri()
    flow = _build_flow(state=state, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    save_credentials(flow.credentials)
    request.session.pop('google_oauth_state', None)
    request.session.pop('google_oauth_redirect_uri', None)
    return flow.credentials


def disconnect_credentials():
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()


def build_frontend_redirect(params):
    query_string = urlencode(params)
    return f"{settings.VITE_SERVER_URL}/?{query_string}"


def get_connection_status():
    if not is_oauth_configured():
        return {
            'connected': False,
            'configured': False,
            'error': (
                'Google OAuth is not configured. Add client.json at '
                f'{CLIENT_SECRETS_PATH} or set GOOGLE_CLIENT_ID and '
                'GOOGLE_CLIENT_SECRET, then restart Django.'
            ),
            'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        }

    credentials = load_credentials()
    if not credentials:
        return {
            'connected': False,
            'configured': True,
            'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
        }

    return {
        'connected': True,
        'configured': True,
        'expired': bool(credentials.expired),
        'scopes': list(credentials.scopes or []),
        'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
    }
