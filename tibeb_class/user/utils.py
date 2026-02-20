import requests
from django.conf import settings


def _normalize_msisdn(to: str) -> str:
    msisdn = str(to or "").strip()
    if msisdn.startswith("+"):
        msisdn = msisdn[1:]
    if msisdn.startswith("0"):
        msisdn = f"251{msisdn[1:]}"
    return msisdn


def _send_sms_afromessage(to, message: str):
    session = requests.Session()
    base_url = "https://api.afromessage.com/api/send"

    url = "%s?from=%s&to=%s&message=%s" % (
        base_url,
        settings.AFROMESSAGE_FROM,
        to,
        message,
    )
    headers = {'Authorization': f'Bearer {settings.AFROMESSAGE_TOKEN}'}

    try:
        result = session.get(url, headers=headers, timeout=15)
        return result.status_code
    except Exception as e:
        return None


def _send_sms_smsethiopia(to, message: str):
    api_key = (getattr(settings, "SMS_ETHIOPIA_API_KEY", "") or "").strip()
    if not api_key:
        return None

    payload = {
        "msisdn": _normalize_msisdn(to),
        "text": message,
    }
    headers = {
        "KEY": api_key,
    }

    try:
        result = requests.post(
            getattr(settings, "SMS_ETHIOPIA_URL", "https://smsethiopia.et/api/sms/send"),
            headers=headers,
            json=payload,
            timeout=15,
        )
        return result.status_code
    except Exception:
        return None


def send_sms_otp(to, message: str):
    provider = (getattr(settings, "SMS_PROVIDER", "afromessage") or "afromessage").strip().lower()

    if provider == "smsethiopia":
        return _send_sms_smsethiopia(to, message)

    return _send_sms_afromessage(to, message)
