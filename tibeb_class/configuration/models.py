from django.db import models

class Configuration(models.Model):
    """
    Stores global configuration values (only one row usually).
    Example: feature toggles, platform settings, etc.
    """
    enable_subscription = models.BooleanField(default=True)
    enable_registration = models.BooleanField(default=True)
    maintenance_mode = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Configuration (updated {self.updated_at:%Y-%m-%d %H:%M})"
