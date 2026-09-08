import os
import json
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2

from django.core.management.base import BaseCommand
from django.conf import settings
from django.contrib.gis.geos import LineString as GEOSLineString, MultiPolygon, Polygon

from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
    OperationalStatus,
    PhysicalCondition,
    HazardLevel,
    RiskLevel,
)
from apps.routes.services.routing.graph import RoadNetworkGraphService


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


class Command(BaseCommand):
    help = "Ingest genuine OSM road network connecting Guwahati, Shillong, and Dimapur."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing infrastructure records before importing',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Ingesting Expanded Northeast Road Network (Guwahati - Shillong - Dimapur) ==="))

        # 1. Ensure Regional Districts Exist
        districts_data = [
            {
                'name': 'Kamrup Metropolitan',
                'state': 'Assam',
                'accessibility_score': 9.0,
                'polygon': Polygon(((91.50, 26.00), (91.95, 26.00), (91.95, 26.35), (91.50, 26.35), (91.50, 26.00))),
            },
            {
                'name': 'Ri-Bhoi',
                'state': 'Meghalaya',
                'accessibility_score': 7.8,
                'polygon': Polygon(((91.70, 25.65), (92.15, 25.65), (92.15, 26.05), (91.70, 26.05), (91.70, 25.65))),
            },
            {
                'name': 'East Khasi Hills',
                'state': 'Meghalaya',
                'accessibility_score': 8.5,
                'polygon': Polygon(((91.70, 25.30), (92.15, 25.30), (92.15, 25.70), (91.70, 25.70), (91.70, 25.30))),
            },
            {
                'name': 'Morigaon',
                'state': 'Assam',
                'accessibility_score': 8.0,
                'polygon': Polygon(((92.00, 26.05), (92.45, 26.05), (92.45, 26.35), (92.00, 26.35), (92.00, 26.05))),
            },
            {
                'name': 'Nagaon',
                'state': 'Assam',
                'accessibility_score': 8.2,
                'polygon': Polygon(((92.40, 26.05), (93.10, 26.05), (93.10, 26.45), (92.40, 26.45), (92.40, 26.05))),
            },
            {
                'name': 'Karbi Anglong',
                'state': 'Assam',
                'accessibility_score': 7.6,
                'polygon': Polygon(((93.00, 25.60), (93.65, 25.60), (93.65, 26.20), (93.00, 26.20), (93.00, 25.60))),
            },
            {
                'name': 'Dimapur',
                'state': 'Nagaland',
                'accessibility_score': 8.0,
                'polygon': Polygon(((93.60, 25.70), (93.95, 25.70), (93.95, 26.05), (93.60, 26.05), (93.60, 25.70))),
            },
        ]

        districts = {}
        for d in districts_data:
            obj, _ = District.objects.update_or_create(
                name=d['name'],
                defaults={
                    'state': d['state'],
                    'accessibility_score': d['accessibility_score'],
                    'geom': MultiPolygon(d['polygon']),
                }
            )
            districts[d['name']] = obj

        def assign_district(lat, lng):
            if lng >= 93.65:
                return districts['Dimapur']
            elif lng >= 93.00:
                return districts['Karbi Anglong']
            elif lng >= 92.40:
                return districts['Nagaon']
            elif lng >= 92.00:
                return districts['Morigaon']
            elif lat <= 25.63 and lng <= 92.00:
                return districts['East Khasi Hills']
            elif lat <= 26.00 and lng <= 92.00:
                return districts['Ri-Bhoi']
            else:
                return districts['Kamrup Metropolitan']

        data_path = os.path.join(settings.BASE_DIR, 'data', 'geospatial', 'ner_osm_highways.json')
        if not os.path.exists(data_path):
            data_path = os.path.join(settings.BASE_DIR, 'ner_osm_highways.json')

        self.stdout.write(f"Loading OSM data from {data_path}...")
        with open(data_path, 'r', encoding='utf-8') as f:
            osm_data = json.load(f)

        nodes = {}
        ways = []
        node_usage = defaultdict(int)

        for el in osm_data.get('elements', []):
            if el['type'] == 'node':
                nodes[el['id']] = (el['lat'], el['lon'])
            elif el['type'] == 'way':
                ways.append(el)
                for nid in el.get('nodes', []):
                    node_usage[nid] += 1

        self.stdout.write(f"Parsed {len(nodes)} OSM nodes and {len(ways)} OSM ways.")

        # Clear existing Infrastructure
        deleted_count, _ = Infrastructure.objects.all().delete()
        self.stdout.write(self.style.WARNING(f"Cleared {deleted_count} existing infrastructure records."))

        created_infras = []
        seen_segs = set()

        for way in ways:
            way_nodes = way.get('nodes', [])
            tags = way.get('tags', {})
            highway = tags.get('highway', '')
            name = tags.get('name', '')
            if not name:
                ref = tags.get('ref', '')
                name = f"{ref} Highway" if ref else f"OSM Way {way['id']}"

            oneway = tags.get('oneway') in ['yes', '1', 'true'] or highway in ['motorway', 'motorway_link']
            osm_way_id = way['id']

            split_indices = [0]
            for idx in range(1, len(way_nodes) - 1):
                nid = way_nodes[idx]
                if node_usage[nid] > 1:
                    split_indices.append(idx)
            split_indices.append(len(way_nodes) - 1)

            for s_idx in range(len(split_indices) - 1):
                i_start = split_indices[s_idx]
                i_end = split_indices[s_idx + 1]
                if i_start == i_end:
                    continue
                seg_nodes = way_nodes[i_start : i_end + 1]
                u = seg_nodes[0]
                v = seg_nodes[-1]
                if u == v or u not in nodes or v not in nodes:
                    continue

                sig = (min(u, v), max(u, v), osm_way_id)
                if sig in seen_segs:
                    continue
                seen_segs.add(sig)

                coords = [nodes[nid] for nid in seg_nodes if nid in nodes]
                if len(coords) < 2:
                    continue

                length_km = 0.0
                for c_i in range(len(coords) - 1):
                    length_km += haversine(coords[c_i][0], coords[c_i][1], coords[c_i + 1][0], coords[c_i + 1][1])
                if length_km < 0.001:
                    length_km = 0.001

                base_speed = 50.0
                rc = RoadClassification.MAJOR_DISTRICT_ROAD
                if highway in ['motorway', 'motorway_link', 'trunk', 'trunk_link']:
                    rc = RoadClassification.NATIONAL_HIGHWAY
                    base_speed = 65.0
                elif highway in ['primary', 'primary_link']:
                    rc = RoadClassification.STATE_HIGHWAY
                    base_speed = 55.0
                elif highway in ['secondary', 'secondary_link']:
                    rc = RoadClassification.MAJOR_DISTRICT_ROAD
                    base_speed = 45.0
                elif highway in ['tertiary', 'tertiary_link']:
                    rc = RoadClassification.RURAL_ROAD
                    base_speed = 35.0

                base_travel_time_min = (length_km / base_speed) * 60.0

                geos_geom = GEOSLineString([(c[1], c[0]) for c in coords], srid=4326)
                mid_lat, mid_lng = coords[len(coords) // 2]
                district = assign_district(mid_lat, mid_lng)

                created_infras.append(Infrastructure(
                    district=district,
                    name=name[:255],
                    infra_type=InfrastructureType.ROAD,
                    road_classification=rc,
                    start_node=u,
                    end_node=v,
                    oneway=oneway,
                    length_km=round(length_km, 3),
                    base_speed_kmh=base_speed,
                    base_travel_time_min=round(base_travel_time_min, 2),
                    osm_way_id=osm_way_id,
                    geom=geos_geom,
                    status=OperationalStatus.ACCESSIBLE,
                    condition=PhysicalCondition.GOOD,
                    landslide_susceptibility=HazardLevel.LOW,
                    flood_hazard_zone=HazardLevel.LOW,
                    historical_landslide_count=0,
                    risk_score=0.0,
                    risk_level=RiskLevel.LOW,
                ))

        self.stdout.write(f"Bulk creating {len(created_infras)} Infrastructure records...")
        Infrastructure.objects.bulk_create(created_infras, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"Successfully inserted {Infrastructure.objects.count()} Infrastructure segments."))

        # Clear and rebuild graph
        RoadNetworkGraphService.clear_graph_cache()
        G = RoadNetworkGraphService.get_graph()
        self.stdout.write(self.style.SUCCESS(f"RoadNetworkGraphService successfully rebuilt: {len(G.nodes)} nodes, {len(G.edges)} edges."))
