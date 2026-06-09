import logging

from django.core.management.base import BaseCommand

from subscription.models import Payment
from subscription.receipt_storage import LOCAL_RECEIPT_PREFIX, move_subscription_receipt_to_default_storage


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Move locally saved subscription receipt files to the configured default storage."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        dry_run = options["dry_run"]
        payments = (
            Payment.objects.filter(receipt_file__startswith=f"{LOCAL_RECEIPT_PREFIX}/")
            .order_by("receipt_uploaded_at", "id")[:limit]
        )

        moved = 0
        failed = 0
        for payment in payments:
            self.stdout.write(f"Payment {payment.id}: {payment.receipt_file.name}")
            if dry_run:
                continue
            try:
                remote_name = move_subscription_receipt_to_default_storage(payment)
                if remote_name:
                    moved += 1
                    logger.info("Subscription local receipt moved. payment_id=%s remote=%s", payment.id, remote_name)
                    self.stdout.write(self.style.SUCCESS(f"  moved -> {remote_name}"))
            except Exception as exc:
                failed += 1
                logger.exception("Subscription local receipt move failed. payment_id=%s", payment.id)
                self.stdout.write(self.style.ERROR(f"  failed: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"Done. moved={moved} failed={failed} dry_run={dry_run}"))
