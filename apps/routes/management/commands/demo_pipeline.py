"""
Phase 5 -- End-to-End Intelligence Pipeline Demo Command.

Demonstrates the complete operational workflow:
  1. Field Officer submits geo-tagged photo report on NH-06
  2. System spatially snaps it to the nearest road segment
  3. Risk engine recalculates -- segment risk surges to HIGH
  4. Road graph rebuilds with elevated edge costs
  5. Route ranker re-picks the safe detour over the highway
  6. AI-02 ETA service estimates delay for an active trip

Run: python manage.py demo_pipeline
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.gis.geos import LineString, MultiPolygon, Point, Polygon
from django.utils import timezone

from apps.accounts.models import Role
from apps.reports.models import IncidentReport, IncidentType, SeverityLevel
from apps.routes.models import (
    District,
    HazardLevel,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
)
from apps.routes.services.risk import RiskPredictionService
from apps.routes.services.routing.graph import RoadNetworkGraphService
from apps.routes.services.route_ranking import RouteRankingService
from apps.vehicles.services.eta import ETAEstimationService


class Command(BaseCommand):
    help = "Demonstrate the end-to-end Phase 5 intelligence pipeline on the NH-06 pilot corridor."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("\n=== PHASE 5: End-to-End Intelligence Pipeline Demo ===\n"))

        # Setup: 3-node dedicated corridor
        poly = Polygon(((92.00, 26.30), (92.30, 26.30), (92.30, 26.60), (92.00, 26.60), (92.00, 26.30)))
        district, _ = District.objects.update_or_create(
            name="Demo Pilot District",
            defaults={"state": "Assam", "accessibility_score": 8.5, "geom": MultiPolygon(poly)},
        )

        highway, _ = Infrastructure.objects.update_or_create(
            name="[Demo] NH-06 Highway Sector (N1-N2)",
            defaults={
                "district": district,
                "infra_type": InfrastructureType.ROAD,
                "road_classification": RoadClassification.NATIONAL_HIGHWAY,
                "start_node": "DEMO_N1",
                "end_node": "DEMO_N2",
                "length_km": 17.0,
                "base_speed_kmh": 50.0,
                "landslide_susceptibility": HazardLevel.MEDIUM,
                "flood_hazard_zone": HazardLevel.LOW,
                "historical_landslide_count": 1,
                "recent_rainfall_mm": 38.0,
                "weather_warning": False,
                "geom": LineString([(92.05, 26.50), (92.12, 26.47), (92.18, 26.42)]),
            },
        )
        RiskPredictionService.assess_and_update(highway)

        connector, _ = Infrastructure.objects.update_or_create(
            name="[Demo] NH-06 Connector Sector (N2-N3)",
            defaults={
                "district": district,
                "infra_type": InfrastructureType.ROAD,
                "road_classification": RoadClassification.NATIONAL_HIGHWAY,
                "start_node": "DEMO_N2",
                "end_node": "DEMO_N3",
                "length_km": 8.0,
                "base_speed_kmh": 50.0,
                "landslide_susceptibility": HazardLevel.LOW,
                "flood_hazard_zone": HazardLevel.LOW,
                "historical_landslide_count": 0,
                "recent_rainfall_mm": 0.0,
                "weather_warning": False,
                "geom": LineString([(92.18, 26.42), (92.22, 26.38), (92.25, 26.34)]),
            },
        )
        RiskPredictionService.assess_and_update(connector)

        bypass, _ = Infrastructure.objects.update_or_create(
            name="[Demo] SH-11 Safe Bypass (N1-N3 Direct)",
            defaults={
                "district": district,
                "infra_type": InfrastructureType.ROAD,
                "road_classification": RoadClassification.STATE_HIGHWAY,
                "start_node": "DEMO_N1",
                "end_node": "DEMO_N3",
                "length_km": 30.0,
                "base_speed_kmh": 45.0,
                "landslide_susceptibility": HazardLevel.LOW,
                "flood_hazard_zone": HazardLevel.LOW,
                "historical_landslide_count": 0,
                "recent_rainfall_mm": 0.0,
                "weather_warning": False,
                "geom": LineString([(92.05, 26.50), (92.15, 26.35), (92.25, 26.34)]),
            },
        )
        RiskPredictionService.assess_and_update(bypass)

        highway.refresh_from_db()
        connector.refresh_from_db()
        bypass.refresh_from_db()

        # BEFORE state
        self.stdout.write(self.style.WARNING("[ BEFORE Field Report ]"))
        self._print_segment(highway)
        self._print_segment(connector)
        self._print_segment(bypass)

        before_candidates = RoadNetworkGraphService.generate_candidate_routes("DEMO_N1", "DEMO_N3")
        before_ranked = RouteRankingService.rank_routes(before_candidates)
        before_rec = next(c for c in before_ranked if c.recommended)
        self.stdout.write(f"  Recommended Route: {before_rec.name} ({before_rec.route_id})")
        self.stdout.write(f"  Distance: {before_rec.distance_km:.1f} km | Base ETA: {before_rec.base_eta_minutes:.1f} min | Risk: {before_rec.risk_level.upper()} ({before_rec.risk_score:.1f}/100)\n")

        # Step 1: Field Officer submits incident
        self.stdout.write(self.style.NOTICE("[STEP 1] Field Officer submits CRITICAL landslide report on NH-06..."))
        officer, _ = User.objects.get_or_create(username="demo_officer_p5")
        if not hasattr(officer, "profile"):
            officer.save()
        officer.profile.role = Role.FIELD_OFFICER
        officer.profile.save()

        report = IncidentReport.objects.create(
            officer=officer,
            photo="reports/photos/demo/placeholder.jpg",
            location=Point(92.12, 26.47, srid=4326),
            description="Major landslide blocking NH-06 at hill pass.",
            incident_type=IncidentType.LANDSLIDE,
            severity=SeverityLevel.CRITICAL,
            client_timestamp=timezone.now(),
            ai_issue_type=IncidentType.LANDSLIDE,
            ai_severity=SeverityLevel.CRITICAL,
            ai_confidence=0.96,
        )
        self.stdout.write(self.style.SUCCESS(f"  Report #{report.pk}: Landslide | CRITICAL | AI confidence=0.96"))

        # Step 2: Spatial snap
        self.stdout.write(self.style.NOTICE("[STEP 2] Spatially snapping report to nearest road segment..."))
        from apps.reports.services.spatial_snap import snap
        snap(report)
        report.refresh_from_db()
        snapped_name = report.snapped_infrastructure.name if report.snapped_infrastructure else "None"
        self.stdout.write(self.style.SUCCESS(f"  Snapped to: \"{snapped_name}\""))

        # Step 3: Risk after snap
        self.stdout.write(self.style.NOTICE("[STEP 3] Risk engine output after snapping..."))
        highway.refresh_from_db()
        self._print_segment(highway)
        self.stdout.write(f"    Risk factors: {', '.join(highway.top_factors)}")

        # Step 4-5: Route reranking
        self.stdout.write(self.style.NOTICE("[STEP 4-5] Rebuilding graph and reranking routes..."))
        after_candidates = RoadNetworkGraphService.generate_candidate_routes("DEMO_N1", "DEMO_N3")
        after_ranked = RouteRankingService.rank_routes(after_candidates)
        after_rec = next(c for c in after_ranked if c.recommended)
        self.stdout.write(self.style.SUCCESS(f"  Recommended Route: {after_rec.name} ({after_rec.route_id})"))
        self.stdout.write(f"  Distance: {after_rec.distance_km:.1f} km | Base ETA: {after_rec.base_eta_minutes:.1f} min | Risk: {after_rec.risk_level.upper()} ({after_rec.risk_score:.1f}/100)")
        self.stdout.write(f"  Explanation: {after_rec.explanation}")

        # Step 6: ETA
        self.stdout.write(self.style.NOTICE("[STEP 6] Condition-aware ETA estimation on recommended route..."))
        segments = [
            {
                "length_km": seg["length_km"],
                "road_classification": "national_highway",
                "risk_score": seg["risk_score"],
                "status": seg["status"],
            }
            for seg in after_rec.segments
        ]
        eta = ETAEstimationService.calculate_eta_for_route(
            segments=segments,
            weather_warning=False,
            rainfall_mm=0.0,
        )
        self.stdout.write(self.style.SUCCESS(
            f"  Base ETA: {eta['base_eta_minutes']:.1f} min | "
            f"Predicted ETA: {eta['predicted_eta_minutes']:.1f} min | "
            f"Delay: {eta['expected_delay_minutes']:.1f} min ({eta['delay_severity'].upper()})"
        ))

        # Summary
        self.stdout.write(self.style.NOTICE("\n=== PIPELINE SUMMARY ==="))
        self.stdout.write(f"  BEFORE: {before_rec.name} (Risk: {before_rec.risk_level.upper()}, Score: {before_rec.risk_score:.1f})")
        self.stdout.write(f"  AFTER:  {after_rec.name} (Risk: {after_rec.risk_level.upper()}, Score: {after_rec.risk_score:.1f})")
        if before_rec.route_id != after_rec.route_id:
            self.stdout.write(self.style.SUCCESS(
                "  [SUCCESS] Route recommendation AUTOMATICALLY SWITCHED from Highway to Safe Bypass after field report!"
            ))
        else:
            self.stdout.write(self.style.WARNING("  Route recommendation unchanged."))

        # Cleanup
        report.delete()
        highway.delete()
        connector.delete()
        bypass.delete()
        district.delete()
        self.stdout.write(self.style.NOTICE("\nDemo entities and report cleaned up successfully.\n"))

    def _print_segment(self, seg):
        self.stdout.write(f"  [{seg.name}] risk={seg.risk_score} ({seg.risk_level.upper()}) status={seg.status}")
