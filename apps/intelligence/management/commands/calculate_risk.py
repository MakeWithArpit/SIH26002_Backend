"""
Management command: calculate_risk

Calculates infrastructure-level disruption risk using the Intelligence Risk Engine.
Evaluates static landslide hazard enrichment and dynamic district weather observations.

Supports:
  python manage.py calculate_risk
  python manage.py calculate_risk --infrastructure <id>
  python manage.py calculate_risk --dry-run
"""
from django.core.management.base import BaseCommand, CommandError
from apps.routes.models import Infrastructure
from apps.intelligence.services.risk import RiskEngine, get_risk_config


class Command(BaseCommand):
    help = "Calculate and optionally persist infrastructure disruption risk scores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--infrastructure",
            type=int,
            default=None,
            help="Optional ID of a specific Infrastructure segment to evaluate.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Calculate risk and display explainable results without saving changes to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        infra_id = options["infrastructure"]
        config = get_risk_config()

        mode_str = "DRY-RUN (No DB changes)" if dry_run else "LIVE PERSISTENCE"
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Infrastructure Risk Engine [{mode_str}] ==="))

        if infra_id is not None:
            try:
                segments = [Infrastructure.objects.select_related("district").get(pk=infra_id)]
            except Infrastructure.DoesNotExist:
                raise CommandError(f"Infrastructure segment #{infra_id} does not exist.")
        else:
            segments = list(Infrastructure.objects.select_related("district").all().order_by("id"))

        if not segments:
            self.stdout.write(self.style.WARNING("No infrastructure segments found."))
            return

        self.stdout.write(f"Targeting {len(segments)} segment(s)...\n")

        counts = {"low": 0, "medium": 0, "high": 0}
        results = []

        for infra in segments:
            district_name = infra.district.name if infra.district else "N/A"
            latest_weather = getattr(infra.district, "latest_weather", None) if infra.district else None
            rain_val = f"{latest_weather.rainfall_mm:.1f} mm" if (latest_weather and latest_weather.rainfall_mm is not None) else "N/A (unavailable)"
            hist_count = max(getattr(infra, "historical_landslide_count", 0) or 0, getattr(infra, "landslide_nearby_count", 0) or 0)
            susc = infra.landslide_susceptibility or "none"

            if dry_run:
                assessment = RiskEngine.assess(infra, config=config)
            else:
                updated_infra = RiskEngine.assess_and_update(infra, config=config)
                assessment = updated_infra.last_assessment

            counts[assessment.level] = counts.get(assessment.level, 0) + 1

            contributing = [
                f"{f.name}: +{f.contribution:.1f} ({f.reason})"
                for f in assessment.factors
                if f.contribution > 0
            ]
            contributing_str = "; ".join(contributing) if contributing else "None (baseline 0.0)"

            results.append({
                "id": infra.id,
                "name": infra.name,
                "district": district_name,
                "susceptibility": susc,
                "historical_landslides": hist_count,
                "rainfall_24h": rain_val,
                "score": assessment.score,
                "level": assessment.level.upper(),
                "contributing": contributing_str,
                "all_factors": assessment.factors,
            })

            # Formatted per-segment output
            level_style = (
                self.style.SUCCESS if assessment.level == "low"
                else self.style.WARNING if assessment.level == "medium"
                else self.style.ERROR
            )

            self.stdout.write(
                f"[{infra.id:2d}] {infra.name} | District: {district_name}\n"
                f"     Susceptibility: {susc.upper():<6} | Historical Landslides: {hist_count} | 24h Rain: {rain_val}\n"
                f"     Risk Score: {assessment.score:.1f}/100 -> {level_style(assessment.level.upper())}\n"
                f"     Contributing Factors: {contributing_str}\n"
            )

        # Summary
        self.stdout.write(self.style.MIGRATE_HEADING("=== Risk Calculation Summary ==="))
        self.stdout.write(f"Total Segments Evaluated: {len(segments)}")
        self.stdout.write(f"  - LOW    (0–39):   {counts['low']}")
        self.stdout.write(f"  - MEDIUM (40–69):  {counts['medium']}")
        self.stdout.write(f"  - HIGH   (70–100): {counts['high']}")
        if dry_run:
            self.stdout.write(self.style.NOTICE("\n[DRY-RUN] No database modifications were persisted."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Successfully persisted risk assessments for {len(segments)} segment(s)."))
