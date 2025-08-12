# signals.py
from django.core.mail import send_mail
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.utils.html import strip_tags
from tibeb_class.email_templates import EmailTemplateHelper
from .models import CustomUser
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives


@receiver(post_save, sender=CustomUser)
def send_verification_email(sender, instance, created, **kwargs):
    if created and instance.email:
        # Manually build the domain (or pull from frontend setting)
        domain = settings.FRONTEND_URL  # e.g., from settings.FRONTEND_URL
        uid = urlsafe_base64_encode(force_bytes(instance.pk))
        token = default_token_generator.make_token(instance)

        verification_link = f"{domain}/verify-email/{uid}/{token}/"
        html = EmailTemplateHelper.verify_email_html(verification_link)
        text = strip_tags(html)
        msg = EmailMultiAlternatives(
            subject="Verify Your Email",
            body=text,  # plain-text
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[instance.email],
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)

