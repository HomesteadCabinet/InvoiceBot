from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invoices'

    def ready(self):
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return

        from .services import start_autoprocess_worker
        start_autoprocess_worker()
