import osmnx as ox
from shapely.geometry import LineString
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import LineString as GEOSLineString, MultiPolygon, Polygon

from apps.routes.models import (
    District,
    Infrastructure,
    InfrastructureType,
    RoadClassification,
)
from apps.routes.services.routing.graph import RoadNetworkGraphService

class Command(BaseCommand):
    help = 'Import real OSM road network using OSMnx'

    def add_arguments(self, parser):
        parser.add_argument(
            '--place', 
            type=str, 
            default='Nongpoh, Meghalaya, India', 
            help='Place name to download'
        )

    def handle(self, *args, **options):
        place_name = options['place']
        self.stdout.write(self.style.NOTICE(f"Downloading OSM road network for: {place_name}..."))
        
        # Retrieve or create a district for imported data with valid boundary geometry
        dummy_poly = Polygon(((91.80, 25.50), (91.95, 25.50), (91.95, 25.65), (91.80, 25.65), (91.80, 25.50)))
        district, _ = District.objects.get_or_create(
            name='Ri-Bhoi (OSM Imported)',
            defaults={
                'state': 'Meghalaya',
                'accessibility_score': 8.0,
                'geom': MultiPolygon(dummy_poly),
            }
        )

        try:
            # network_type='drive' fetches drivable public streets
            G = ox.graph_from_place(place_name, network_type='drive', simplify=True)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to retrieve OSM data: {e}"))
            return
            
        self.stdout.write(f"Downloaded network with {len(G.nodes)} nodes and {len(G.edges)} edges.")
        
        processed_edges = set()
        created_count = 0
        updated_count = 0
        
        for u, v, key, data in G.edges(keys=True, data=True):
            osmids = data.get('osmid', 0)
            way_id = osmids[0] if isinstance(osmids, list) else osmids
            
            # Deterministic source-level identity
            # Two-way roads produce u->v and v->u edges in osmnx, but both share the same min/max nodes and key.
            min_node = min(u, v)
            max_node = max(u, v)
            osm_segment_id = f"{way_id}-{min_node}-{max_node}-{key}"
            
            # To avoid creating two Infrastructure records for a two-way road in the same run,
            # we track the deterministic identity.
            if osm_segment_id in processed_edges:
                continue
            processed_edges.add(osm_segment_id)
            
            oneway = data.get('oneway', False)
            length_m = data.get('length', 0.0)
            length_km = length_m / 1000.0
            
            # Geometry
            geom = data.get('geometry')
            if geom:
                coords = list(geom.coords)
            else:
                u_data = G.nodes[u]
                v_data = G.nodes[v]
                coords = [(u_data['x'], u_data['y']), (v_data['x'], v_data['y'])]
            
            geos_line = GEOSLineString(coords, srid=4326)
            
            highway = data.get('highway', '')
            if isinstance(highway, list):
                highway = highway[0]
            
            # Map road type
            rc = RoadClassification.RURAL_ROAD
            if highway in ['trunk', 'primary', 'primary_link', 'trunk_link']:
                rc = RoadClassification.NATIONAL_HIGHWAY
            elif highway in ['secondary', 'secondary_link']:
                rc = RoadClassification.STATE_HIGHWAY
            elif highway in ['tertiary', 'tertiary_link']:
                rc = RoadClassification.MAJOR_DISTRICT_ROAD
                
            name = data.get('name', f"OSM Way {way_id}")
            if isinstance(name, list):
                name = name[0]
            
            maxspeed = data.get('maxspeed', '50')
            if isinstance(maxspeed, list):
                maxspeed = maxspeed[0]
            try:
                base_speed = float(maxspeed)
            except ValueError:
                base_speed = 50.0
                
            base_travel_time = (length_km / base_speed) * 60.0 if base_speed > 0 else 0
            
            # Repeated import handling: Upsert via deterministic identity
            existing = Infrastructure.objects.filter(osm_segment_id=osm_segment_id).first()
            
            if existing:
                existing.oneway = oneway
                existing.geom = geos_line
                existing.length_km = length_km
                existing.base_speed_kmh = base_speed
                existing.base_travel_time_min = base_travel_time
                existing.road_classification = rc
                existing.name = name
                existing.save()
                updated_count += 1
            else:
                Infrastructure.objects.create(
                    district=district,
                    name=name,
                    infra_type=InfrastructureType.ROAD,
                    road_classification=rc,
                    start_node=min_node, # Ensure consistency
                    end_node=max_node,   # Ensure consistency
                    oneway=oneway,
                    osm_way_id=way_id,
                    osm_segment_id=osm_segment_id,
                    length_km=length_km,
                    base_speed_kmh=base_speed,
                    base_travel_time_min=base_travel_time,
                    geom=geos_line
                )
                created_count += 1
                
        # Invalidate in-memory graph cache to ensure fresh topology on next request
        RoadNetworkGraphService.clear_graph_cache()
        self.stdout.write(self.style.SUCCESS(f"Successfully processed OSM data. Created: {created_count}, Updated: {updated_count} segments."))
