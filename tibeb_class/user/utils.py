import requests
from django.conf import settings

def send_sms_otp(to, message: str):
    session = requests.Session()
    base_url = "https://api.afromessage.com/api/send"

    url = "%s?from=%s&to=%s&message=%s" % (
        base_url,
        settings.AFROMESSAGE_FROM,
        to,
        message,
    )
    headers = {'Authorization': f'Bearer {settings.AFROMESSAGE_TOKEN}'}

    # Debug

    try:
        result = session.get(url, headers=headers)
        return result.status_code
    except Exception as e:
        return None
