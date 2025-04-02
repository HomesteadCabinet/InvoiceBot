# frontend_views.py
import requests
from django.http import StreamingHttpResponse, HttpResponseNotFound
from django.views import View
from django.conf import settings
from django.middleware.csrf import get_token


class FrontendProxyView(View):
    def get(self, request, path=""):
        vite_server_url = settings.VITE_SERVER_URL

        # Build the target URL, including any query string
        query_string = request.META.get("QUERY_STRING", "")
        target_url = f"{vite_server_url}/{path}"
        if query_string:
            target_url += f"?{query_string}"

        # Prepare headers to ensure Vite accepts the request
        # Strip the protocol from vite_server_url for the Host header
        host_header = vite_server_url.replace("http://", "").replace("https://", "")
        headers = {
            "User-Agent": request.META.get("HTTP_USER_AGENT", ""),
            "Accept": request.META.get("HTTP_ACCEPT", ""),
            "Host": host_header,
            "X-CSRFToken": get_token(request),  # Add CSRF token to headers
        }

        try:
            # Get CSRF token and set cookie in the response
            csrf_token = get_token(request)

            resp = requests.get(target_url, headers=headers, stream=True)
            response = StreamingHttpResponse(
                resp.iter_content(chunk_size=8192),
                status=resp.status_code,
                content_type=resp.headers.get("Content-Type", "text/html")
            )
            # Forward additional headers as needed
            for header in ["Cache-Control", "Content-Length"]:
                if header in resp.headers:
                    response[header] = resp.headers[header]

            # Set CSRF cookie in the response
            response.set_cookie('csrftoken', csrf_token)

            return response
        except requests.ConnectionError:
            return HttpResponseNotFound("Vite dev server is not running.")
