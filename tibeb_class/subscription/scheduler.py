from apscheduler.schedulers.background import BackgroundScheduler
from django.utils import timezone
from datetime import date
from .models import Payment

def update_subscription_statuses():
    """Expire old subscriptions and activate the next pending one."""
    today = timezone.now().date()
    expired_subs = Payment.objects.filter(
        end_date__lt=today,
        payment_status="completed",
        status="active"
    )
    for sub in expired_subs:
        sub.status = "expired"
        sub.save(update_fields=[ "status"])

        next_sub = (
            Payment.objects
            .filter(user=sub.user, status="pending",payment_status="completed")
            .order_by("start_date")
            .first()
        )
        if next_sub:
            next_sub.status = "active"
            next_sub.save(update_fields=["status"])


def start():
    """Start APScheduler to run every hour."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_subscription_statuses, "interval", hours=1)
    scheduler.start()
