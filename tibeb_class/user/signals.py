# signals.py
from django.core.mail import send_mail
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from .models import CustomUser
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator

@receiver(post_save, sender=CustomUser)
def send_verification_email(sender, instance, created, **kwargs):
    if created and instance.email:
        # Manually build the domain (or pull from frontend setting)
        domain = settings.FRONTEND_URL  # e.g., from settings.FRONTEND_URL
        uid = urlsafe_base64_encode(force_bytes(instance.pk))
        token = default_token_generator.make_token(instance)

        verification_link = f"{domain}/verify-email/{uid}/{token}/"

        send_mail(
            subject='Verify Your Email',
            message=f'Click the link to verify your email: {verification_link}',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
        )

