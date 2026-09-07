"""
Management command: sync_weather

Synchronizes dynamic weather and previous 24-hour rainfall data for corridor districts
using the configured weather provider (Open-Meteo by default).
"""
import sys
from django.core.management.base import BaseCommand, CommandError

from apps.routes.models import District, WeatherSnapshot
from apps.routes.services.weather.service import WeatherService


class Command(BaseCommand):
    help = "Synchronize dynamic weather and 24-hour rainfall from external weather provider."

    def add_arguments(self, parser):
        parser.add_argument(
            '--district',
            type=str,
            default=None,
            help="Optional district ID (integer) or name to synchronize individually.",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help="Fetch and normalize weather data, but do not persist snapshots to database.",
        )
        parser.add_argument(
            '--provider',
            type=str,
            default=None,
            help="Override weather provider ('open_meteo' or 'mock'). Defaults to settings.WEATHER_PROVIDER.",
        )

    def handle(self, *args, **options):
        district_query = options.get('district')
        dry_run = options.get('dry_run', False)
        provider_name = options.get('provider')

        provider = WeatherService.get_provider(provider_name)
        provider_class_name = provider.__class__.__name__

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Dynamic Weather Synchronization ==="))
        self.stdout.write(f"Provider:    {provider_class_name}")
        self.stdout.write(f"Mode:        {'DRY RUN (No DB changes)' if dry_run else 'LIVE PERSISTENCE'}")

        if district_query:
            # Query single district by ID or Name
            try:
                if district_query.isdigit():
                    district = District.objects.get(id=int(district_query))
                else:
                    district = District.objects.get(name__iexact=district_query)
            except District.DoesNotExist:
                raise CommandError(f"District '{district_query}' not found.")

            districts = [district]
        else:
            districts = list(District.objects.all().order_by('id'))

        if not districts:
            self.stdout.write(self.style.WARNING("No districts found in database to synchronize."))
            return

        self.stdout.write(f"Targeting:   {len(districts)} district(s)\n")

        total_success = 0
        total_failed = 0

        for district in districts:
            lat, lng = WeatherService.resolve_district_coordinates(district)
            self.stdout.write(
                f"[{district.id}] District: {district.name} ({district.state})"
            )
            self.stdout.write(f"     Coordinates: lat={lat:.4f}, lng={lng:.4f}")

            try:
                snapshot = WeatherService.sync_district(
                    district=district,
                    provider=provider,
                    dry_run=dry_run,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"     [SUCCESS] 24h Rain: {snapshot.rainfall_mm} mm | "
                        f"Condition: {snapshot.condition.upper()} | "
                        f"Temp: {snapshot.temperature_c}°C | "
                        f"Humidity: {snapshot.humidity_pct}% | "
                        f"Wind: {snapshot.wind_speed_kmh} km/h"
                    )
                )
                self.stdout.write(f"     Recorded At: {snapshot.recorded_at}")
                self.stdout.write(
                    f"     Persisted:   {'SKIPPED (Dry-Run)' if dry_run else f'Snapshot ID #{snapshot.id}'}\n"
                )
                total_success += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"     [FAILED] Error fetching weather: {str(e)}"
                    )
                )
                last_snap = district.latest_weather
                if last_snap:
                    self.stdout.write(
                        f"     Retained Previous Snapshot: {last_snap.condition} "
                        f"({last_snap.rainfall_mm}mm) at {last_snap.recorded_at}\n"
                    )
                else:
                    self.stdout.write("     No previous snapshot on record.\n")
                total_failed += 1

        self.stdout.write(self.style.MIGRATE_HEADING("=== Synchronization Summary ==="))
        self.stdout.write(f"Total:      {len(districts)}")
        self.stdout.write(self.style.SUCCESS(f"Successful: {total_success}"))
        if total_failed > 0:
            self.stdout.write(self.style.ERROR(f"Failed:     {total_failed}"))
        else:
            self.stdout.write(f"Failed:     0")
        self.stdout.write("")

