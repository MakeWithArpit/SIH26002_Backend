"""
Management command to seed the Guwahati – Shillong (NH-06) Pilot Transport Corridor.
Creates pilot districts and realistic connected road segments with topography,
hazard ratings, base speeds, and travel times.
"""
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import MultiPolygon, Polygon, LineString

from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
    HazardLevel,
    OperationalStatus,
    PhysicalCondition,
)
from apps.routes.services.risk import RiskPredictionService


class Command(BaseCommand):
    help = 'Seed the Guwahati-Shillong (NH-06) Pilot Corridor road network graph and districts'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding pilot corridor: Guwahati -> Shillong (NH-06)...'))

        # ── 1. Create Districts ───────────────────────────────────────────
        # Approximate bounding box polygons for the 3 corridor districts
        districts_data = [
            {
                'name': 'Kamrup Metropolitan',
                'state': 'Assam',
                'accessibility_score': 9.2,
                'polygon': Polygon(((91.60, 26.05), (91.95, 26.05), (91.95, 26.25), (91.60, 26.25), (91.60, 26.05))),
            },
            {
                'name': 'Ri-Bhoi',
                'state': 'Meghalaya',
                'accessibility_score': 7.8,
                'polygon': Polygon(((91.70, 25.65), (92.10, 25.65), (92.10, 26.05), (91.70, 26.05), (91.70, 25.65))),
            },
            {
                'name': 'East Khasi Hills',
                'state': 'Meghalaya',
                'accessibility_score': 8.5,
                'polygon': Polygon(((91.75, 25.30), (92.15, 25.30), (92.15, 25.70), (91.75, 25.70), (91.75, 25.30))),
            },
        ]

        districts = {}
        for d in districts_data:
            obj, created = District.objects.update_or_create(
                name=d['name'],
                defaults={
                    'state': d['state'],
                    'accessibility_score': d['accessibility_score'],
                    'geom': MultiPolygon(d['polygon']),
                }
            )
            districts[d['name']] = obj
            status_str = 'Created' if created else 'Updated'
            self.stdout.write(f"  - District: {obj.name} ({status_str})")

        # ── 2. Create Road Segments (Graph Edges) ──────────────────────────
        # LineStrings use (lng, lat) format for GIS standard
        corridor_segments = [
            {
                'name': 'NH-06 Guwahati City to Jorabat Segment',
                'district': districts['Kamrup Metropolitan'],
                'infra_type': InfrastructureType.ROAD,
                'road_classification': RoadClassification.NATIONAL_HIGHWAY,
                'start_node': 'GUW_CITY',
                'end_node': 'GUW_JORABAT',
                'length_km': 16.5,
                'base_speed_kmh': 55.0,
                'landslide_susceptibility': HazardLevel.LOW,
                'flood_hazard_zone': HazardLevel.MEDIUM,
                'historical_landslide_count': 1,
                'geom': LineString([
                    (91.7500, 26.1833),
                    (91.7850, 26.1600),
                    (91.8200, 26.1300),
                    (91.8650, 26.1030),
                ]),
            },
            {
                'name': 'NH-06 Jorabat to Nongpoh Hill Descent',
                'district': districts['Ri-Bhoi'],
                'infra_type': InfrastructureType.ROAD,
                'road_classification': RoadClassification.NATIONAL_HIGHWAY,
                'start_node': 'GUW_JORABAT',
                'end_node': 'MEG_NONGPOH',
                'length_km': 34.0,
                'base_speed_kmh': 45.0,
                'landslide_susceptibility': HazardLevel.HIGH,
                'flood_hazard_zone': HazardLevel.LOW,
                'historical_landslide_count': 4,
                'geom': LineString([
                    (91.8650, 26.1030),
                    (91.8700, 26.0400),
                    (91.8820, 25.9600),
                    (91.8780, 25.9015),
                ]),
            },
            {
                'name': 'Umran River Bridge (NH-06)',
                'district': districts['Ri-Bhoi'],
                'infra_type': InfrastructureType.BRIDGE,
                'road_classification': RoadClassification.NATIONAL_HIGHWAY,
                'start_node': 'MEG_UMRAN_NORTH',
                'end_node': 'MEG_UMRAN_SOUTH',
                'length_km': 0.8,
                'base_speed_kmh': 35.0,
                'landslide_susceptibility': HazardLevel.MEDIUM,
                'flood_hazard_zone': HazardLevel.HIGH,
                'historical_landslide_count': 0,
                'condition': PhysicalCondition.GOOD,
                'geom': LineString([
                    (91.8770, 25.8200),
                    (91.8780, 25.8150),
                    (91.8790, 25.8100),
                ]),
            },
            {
                'name': 'NH-06 Nongpoh to Umiam Lake Sector',
                'district': districts['Ri-Bhoi'],
                'infra_type': InfrastructureType.ROAD,
                'road_classification': RoadClassification.NATIONAL_HIGHWAY,
                'start_node': 'MEG_NONGPOH',
                'end_node': 'MEG_UMIAM',
                'length_km': 32.5,
                'base_speed_kmh': 40.0,
                'landslide_susceptibility': HazardLevel.HIGH,
                'flood_hazard_zone': HazardLevel.LOW,
                'historical_landslide_count': 6,
                'geom': LineString([
                    (91.8780, 25.9015),
                    (91.8900, 25.8000),
                    (91.9100, 25.7200),
                    (91.9050, 25.6680),
                ]),
            },
            {
                'name': 'NH-06 Umiam to Shillong Police Bazar (Main Highway)',
                'district': districts['East Khasi Hills'],
                'infra_type': InfrastructureType.ROAD,
                'road_classification': RoadClassification.NATIONAL_HIGHWAY,
                'start_node': 'MEG_UMIAM',
                'end_node': 'MEG_SHILLONG',
                'length_km': 15.2,
                'base_speed_kmh': 35.0,
                'landslide_susceptibility': HazardLevel.MEDIUM,
                'flood_hazard_zone': HazardLevel.LOW,
                'historical_landslide_count': 2,
                'geom': LineString([
                    (91.9050, 25.6680),
                    (91.9120, 25.6300),
                    (91.9000, 25.6000),
                    (91.8933, 25.5788),
                ]),
            },
            # Alternate detour / bypass segment for Phase 3 route comparison
            {
                'name': 'Shillong Eastern Bypass Detour (Alternative Route)',
                'district': districts['East Khasi Hills'],
                'infra_type': InfrastructureType.ROAD,
                'road_classification': RoadClassification.STATE_HIGHWAY,
                'start_node': 'MEG_UMIAM',
                'end_node': 'MEG_SHILLONG',
                'length_km': 22.0,
                'base_speed_kmh': 50.0,
                'landslide_susceptibility': HazardLevel.LOW,
                'flood_hazard_zone': HazardLevel.LOW,
                'historical_landslide_count': 0,
                'geom': LineString([
                    (91.9050, 25.6680),
                    (91.9500, 25.6500),
                    (91.9600, 25.6000),
                    (91.8933, 25.5788),
                ]),
            },
        ]

        count = 0
        for seg in corridor_segments:
            infra, _ = Infrastructure.objects.update_or_create(
                name=seg['name'],
                defaults=seg,
            )
            # Run initial risk assessment
            RiskPredictionService.assess_and_update(infra)
            count += 1
            self.stdout.write(
                f"  - Infrastructure: {infra.name} | Risk: {infra.risk_level.upper()} ({infra.risk_score})"
            )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully seeded {len(districts)} districts and {count} road segments.')
        )
