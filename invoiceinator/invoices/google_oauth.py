from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets',
]

TOKEN_PATH = Path(settings.BASE_DIR) / 'token.json'
CLIENT_SECRETS_PATH = Path(settings.BASE_DIR) / 'client.json'


def _build_flow(state=None, redirect_uri=None):
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        scopes=SCOPES,
        state=state,
    )
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    return flow


def get_redirect_uri(request):
    return request.build_absolute_uri(reverse('google_oauth_callback'))


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

    flow = _build_flow(state=state, redirect_uri=get_redirect_uri(request))
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
    credentials = load_credentials()
    if not credentials:
        return {
            'connected': False,
        }

    return {
        'connected': True,
        'expired': bool(credentials.expired),
        'scopes': list(credentials.scopes or []),
    }
