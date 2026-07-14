from django.core.management.base import BaseCommand

from apps.reservas.services import liberar_mesas_por_no_asistencia


class Command(BaseCommand):
    help = 'Libera mesas de reservas confirmadas cuyo cliente no asistió tras la tolerancia configurada.'

    def handle(self, *args, **options):
        liberadas = liberar_mesas_por_no_asistencia()
        self.stdout.write(self.style.SUCCESS(f'Reservas marcadas como no asistió: {liberadas}'))
