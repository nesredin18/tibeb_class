from django.conf import settings
from django.http import FileResponse, HttpResponse


# ✅ Custom media server with CORS for HLS and .key files
from django.http import FileResponse, HttpResponse
from django.conf import settings
import os
def serve_media(request, path):
    """Serve media files with proper CORS headers (for encryption keys & segments)."""
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if not os.path.exists(file_path):
        return HttpResponse(status=404)

    # ✅ Handle preflight OPTIONS requests
    if request.method == "OPTIONS":
        response = HttpResponse()
    else:
        response = FileResponse(open(file_path, 'rb'))



    return response