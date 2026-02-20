from django.core.management.base import BaseCommand
from notifications.scheduler import distribute_notifications

class Command(BaseCommand):
    help = "Run notification distributor"

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting notification distribution...")
        distribute_notifications()
        self.stdout.write(self.style.SUCCESS("Notification job finished."))