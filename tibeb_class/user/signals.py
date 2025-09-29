# signals.py
from django.core.mail import send_mail
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.utils.html import strip_tags
from tibeb_class.email_templates import EmailTemplateHelper
from tibeb_class.sms_templates import SMSTemplateHelper
from user.utils import send_sms_otp
from .models import CustomUser, PhoneOTP
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives


@receiver(post_save, sender=CustomUser)
def send_verification_email(sender, instance, created, **kwargs):

    if not created:
        return
    if instance.username_type == 'email':
        otp_obj = PhoneOTP.objects.create(user=instance)
        html = EmailTemplateHelper.verify_email_html(otp_obj.otp)
        text = strip_tags(html)
        msg = EmailMultiAlternatives(
            subject="Verify Your Email",
            body=text,  # plain-text
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[instance.username],  # instance.username is the email
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    elif instance.username_type == 'phone':
        otp_obj = PhoneOTP.objects.create(user=instance)
        msg = SMSTemplateHelper.verification_otp(otp_obj.otp)
        send_sms_otp(instance.username, msg)
    else:
        # Nothing to verify, user created without contact info
        pass

