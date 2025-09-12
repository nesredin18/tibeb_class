from urllib.parse import urljoin
from django.conf import settings
from django.templatetags.static import static
class EmailTemplateHelper:
    @staticmethod
    def _header() -> str:
        logo = urljoin(settings.BACKEND_URL, static("emails/logo.png"))

        return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#FFF8DF;padding:0;font-family:Arial,sans-serif;">
  <tr><td align="center" style="padding:16px 0;">
    <img src="{logo}" alt="Tibeb Class" style="height:40px;display:block;">
  </td></tr>
</table>"""

    @staticmethod
    def _footer() -> str:
        return """
<table width="100%" cellpadding="0" cellspacing="0" style="border-top:1px solid #e5e7eb;padding:0;font-family:Arial,sans-serif;">
  <tr><td align="center" style="padding:8px 0;font-size:12px;color:#9ca3af;">
    <span style="line-height:1.4;">Copyright ©2023 Tibeb Class. All rights reserved.</span>
  </td></tr>
</table>"""

    @staticmethod
    def verify_email_html(verification_link: str) -> str:
        header = EmailTemplateHelper._header()
        footer = EmailTemplateHelper._footer()
        content = f"""
<h1 style="font-size:24px;text-align:center;font-weight:bold;color:#111827;margin:0 0 16px;">
  Verify Your Email
</h1>

<p style="color:#4b5563;font-size:14px;margin:0 0 24px;">
  Thanks for signing up! This is the confirmation code .
</p>
<div style="text-align:center;margin:24px 0 32px;">
  <p style="background-color:#0C3F87;color:#FFFFFF;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;font-size:14px;display:inline-block;">
    {verification_link}
  </p>
</div>


<p style="color:#6b7280;font-size:12px;margin:0;">
  This code will expire soon. If it expires, you can request a new one from the sign-in page.
</p>
"""
        shell = f"""
<div style="font-family:'Roboto',Arial,sans-serif;background-color:#f9fafb;padding:0;margin:0;">
  <div style="max-width:600px;margin:0 auto;background-color:#ffffff;">
    {header}
    <div style="padding:32px 24px;max-width:600px;margin:0 auto;">
      {content}
    </div>
    {footer}
  </div>
</div>
"""
        return shell
    
    @staticmethod
    def forgot_password_html(otp) -> str:
        header = EmailTemplateHelper._header()
        footer = EmailTemplateHelper._footer()
        content = f"""
    <h1 style="font-size:24px;text-align:center;font-weight:bold;color:#111827;margin:0 0 16px;">
    Reset Your Password
    </h1>

    <p style="color:#4b5563;font-size:14px;margin:0 0 24px;">
    We received a request to reset your password. Use the code below to reset your password.
    </p>

    <div style="text-align:center;margin:24px 0 32px;">
    <p
        style="background-color:#0C3F87;color:#FFFFFF;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:bold;font-size:14px;display:inline-block;">
{otp}
            </p>
    </div>

    <p style="color:#6b7280;font-size:12px;margin:0;">
    If you didn’t request a password reset, you can safely ignore this email.
    </p>
    """
        return f"""
    <div style="font-family:'Roboto',Arial,sans-serif;background-color:#f9fafb;padding:0;margin:0;">
    <div style="max-width:600px;margin:0 auto;background-color:#ffffff;">
        {header}
        <div style="padding:32px 24px;max-width:600px;margin:0 auto;">
        {content}
        </div>
        {footer}
    </div>
    </div>
    """


