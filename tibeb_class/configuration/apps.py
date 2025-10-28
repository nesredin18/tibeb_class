from django.apps import AppConfig
from django.core.files.storage import default_storage
from django.conf import settings
import importlib


class ConfigurationConfig(AppConfig):
    name = "configuration"

    def ready(self):
        """
        Ensure default_storage uses TeleCloud OBS instead of FileSystemStorage.
        Works on Django 5.x where get_storage_class was removed.
        """
        try:
            # Dynamically import the configured storage class
            module_path, class_name = settings.DEFAULT_FILE_STORAGE.rsplit('.', 1)
            storage_module = importlib.import_module(module_path)
            storage_class = getattr(storage_module, class_name)

            # Replace the wrapped default_storage instance
            default_storage._wrapped = storage_class()
        except Exception as e:
            print("Could not rebind default storage:", e)
