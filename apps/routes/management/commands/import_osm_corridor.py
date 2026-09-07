import osmnx as ox
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon
from apps.routes.models import (
    Infrastructure,
    District,
    InfrastructureType,
    RoadClassification,
    OperationalStatus,
    PhysicalCondition,
    HazardLevel,
)

class Command(BaseCommand):
    help = "Import OSM road network for a controlled area (Shillong, Meghalaya)"

    def handle(self, *args, **options):
        place_name = "Shillong, Meghalaya, India"
        self.stdout.write(self.style.NOTICE(f"Downloading OSM network for {place_name}..."))
        
        try:
            # network_type="drive" retrieves drivable road topology, preserving directionality
            G = ox.graph_from_place(place_name, network_type="drive")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to retrieve OSM data: {e}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Successfully retrieved OSM graph: {len(G.nodes)} nodes, {len(G.edges)} edges."))

        # Create or get District
        dummy_poly = Polygon(((91.80, 25.50), (91.95, 25.50), (91.95, 25.65), (91.80, 25.65), (91.80, 25.50)))
        district, _ = District.objects.get_or_create(
            name="Shillong OSM Area",
            defaults={
                'state': 'Meghalaya',
                'accessibility_score': 8.5,
                'geom': MultiPolygon(dummy_poly)
            }
        )

        # Clear existing infrastructure for this district to avoid uncontrolled duplicates
        deleted_count, _ = Infrastructure.objects.filter(district=district).delete()
        if deleted_count > 0:
            self.stdout.write(self.style.WARNING(f"Cleared {deleted_count} existing infrastructure records for {district.name}."))

        seen_segments = set()
        created_count = 0

        self.stdout.write("Processing segments and writing to database...")

        for u, v, key, data in G.edges(keys=True, data=True):
            osm_way_id = data.get('osmid')
            if isinstance(osm_way_id, list):
                osm_way_id = osm_way_id[0]
            
            # Unique physical segment signature
            sig = (min(u, v), max(u, v), str(osm_way_id))
            if sig in seen_segments:
                continue
            seen_segments.add(sig)

            oneway = bool(data.get('oneway', False))
            
            # length in meters is automatically calculated by OSMnx
            length_m = data.get('length', 0.0)
            length_km = length_m / 1000.0
            
            # Geometry handling
            if 'geometry' in data:
                coords = list(data['geometry'].coords)
                geom = LineString(coords)
            else:
                u_node = G.nodes[u]
                v_node = G.nodes[v]
                geom = LineString([(u_node['x'], u_node['y']), (v_node['x'], v_node['y'])])

            name = data.get('name', 'Unnamed Road')
            if isinstance(name, list):
                name = name[0]
            if not name:
                name = 'Unnamed Road'

            highway = data.get('highway', '')
            if isinstance(highway, list):
                highway = highway[0]

            road_class = RoadClassification.RURAL_ROAD
            base_speed = 30.0
            if highway in ['trunk', 'trunk_link', 'motorway', 'motorway_link']:
                road_class = RoadClassification.NATIONAL_HIGHWAY
                base_speed = 60.0
            elif highway in ['primary', 'primary_link']:
                road_class = RoadClassification.STATE_HIGHWAY
                base_speed = 50.0
            elif highway in ['secondary', 'secondary_link', 'tertiary', 'tertiary_link']:
                road_class = RoadClassification.MAJOR_DISTRICT_ROAD
                base_speed = 40.0
            
            maxspeed = data.get('maxspeed')
            if maxspeed:
                if isinstance(maxspeed, list):
                    maxspeed = maxspeed[0]
                try:
                    speed_str = str(maxspeed).split()[0]
                    base_speed = float(speed_str)
                except ValueError:
                    pass

            base_travel_time_min = (length_km / base_speed) * 60.0 if base_speed > 0 else 0.0

            Infrastructure.objects.create(
                district=district,
                name=name[:255],
                infra_type=InfrastructureType.ROAD,
                road_classification=road_class,
                start_node=u,
                end_node=v,
                oneway=oneway,
                length_km=length_km,
                base_speed_kmh=base_speed,
                base_travel_time_min=base_travel_time_min,
                osm_way_id=int(osm_way_id) if osm_way_id else None,
                geom=geom,
                status=OperationalStatus.ACCESSIBLE,
                condition=PhysicalCondition.GOOD,
                landslide_susceptibility=HazardLevel.LOW,
                flood_hazard_zone=HazardLevel.LOW,
                historical_landslide_count=0,
                risk_score=0.0
            )
            created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully ingested {created_count} Infrastructure segments."))
