import math
import tempfile
import json
from io import StringIO
from django.test import TestCase
from django.core.management import call_command, CommandError
from django.contrib.gis.geos import LineString, MultiPolygon, Polygon, MultiLineString
import pyproj
from shapely.geometry import Point as ShapelyPoint, LineString as ShapelyLineString

from apps.routes.models import District, Infrastructure, InfrastructureType, RoadClassification, HazardLevel
from apps.routes.serializers import InfrastructureSerializer
from apps.routes.services.spatial_enrichment import SpatialEnrichmentService, SEVERITY_ORDER


class SpatialEnrichmentCoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        dummy_poly = Polygon(((91.70, 25.20), (92.10, 25.20), (92.10, 25.60), (91.70, 25.60), (91.70, 25.20)))
        cls.district = District.objects.create(
            name="Test District",
            state="Meghalaya",
            accessibility_score=8.5,
            geom=MultiPolygon(dummy_poly),
        )

    def _create_infra(self, name: str, geom=None, **kwargs) -> Infrastructure:
        defaults = {
            'district': self.district,
            'name': name,
            'infra_type': InfrastructureType.ROAD,
            'road_classification': RoadClassification.NATIONAL_HIGHWAY,
            'start_node': 1001,
            'end_node': 1002,
            'length_km': 5.0,
            'geom': geom or LineString([(91.85, 25.40), (91.87, 25.42)]),
        }
        defaults.update(kwargs)
        return Infrastructure.objects.create(**defaults)

    def test_road_intersecting_susceptibility_polygon(self):
        """
        1. Test road intersecting a susceptibility polygon:
           - zone_member becomes True
           - correct susceptibility category is selected
        """
        susc_features = [
            {
                "type": "Feature",
                "properties": {"id": "S1", "susceptibility_class": "High"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [91.860, 25.410],
                            [91.880, 25.410],
                            [91.880, 25.430],
                            [91.860, 25.430],
                            [91.860, 25.410],
                        ]
                    ],
                },
            }
        ]
        indices = SpatialEnrichmentService.build_spatial_indices([], susc_features)

        # Road crosses through the susceptibility polygon
        road = self._create_infra(
            "Intersecting Road",
            geom=LineString([(91.850, 25.420), (91.890, 25.420)]),
        )

        SpatialEnrichmentService.enrich_segment(road, indices)

        self.assertTrue(road.landslide_zone_member)
        self.assertEqual(road.landslide_susceptibility, HazardLevel.HIGH)

    def test_road_near_historical_landslide(self):
        """
        2. Test road near a historical landslide:
           - nearby_count is correct
           - historical_landslide_count matches nearby_count
           - metric distance is correct within a sensible floating-point tolerance
        """
        # Landslide at (91.86000, 25.42000)
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1, "name": "Slide 1"},
                "geometry": {"type": "Point", "coordinates": [91.86000, 25.42000]},
            }
        ]
        indices = SpatialEnrichmentService.build_spatial_indices(inv_features, [])

        # Road parallel to landslide, roughly 100m east (~0.001 deg lon at lat 25.42 is ~100.5m)
        road = self._create_infra(
            "Near Road",
            geom=LineString([(91.86100, 25.41900), (91.86100, 25.42100)]),
        )

        SpatialEnrichmentService.enrich_segment(road, indices, threshold_m=500.0)

        self.assertEqual(road.landslide_nearby_count, 1)
        self.assertEqual(road.historical_landslide_count, 1)
        self.assertIsNotNone(road.landslide_nearest_distance_m)
        # Expected distance is approx 100.5 meters; allow reasonable tolerance (80m - 120m)
        self.assertAlmostEqual(road.landslide_nearest_distance_m, 100.5, delta=15.0)

    def test_road_with_no_nearby_landslide(self):
        """
        3. Test road with no nearby landslide:
           - nearby_count == 0
           - historical_landslide_count == 0
           - nearest distance is greater than threshold
        """
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1, "name": "Slide 1"},
                "geometry": {"type": "Point", "coordinates": [91.86000, 25.42000]},
            }
        ]
        indices = SpatialEnrichmentService.build_spatial_indices(inv_features, [])

        # Road > 20km away in another sector
        road = self._create_infra(
            "Far Road",
            geom=LineString([(91.70000, 25.20000), (91.71000, 25.21000)]),
        )

        SpatialEnrichmentService.enrich_segment(road, indices, threshold_m=500.0)

        self.assertEqual(road.landslide_nearby_count, 0)
        self.assertEqual(road.historical_landslide_count, 0)
        self.assertIsNotNone(road.landslide_nearest_distance_m)
        self.assertGreater(road.landslide_nearest_distance_m, 500.0)
        self.assertGreater(road.landslide_nearest_distance_m, 20000.0)

    def test_multiple_nearby_landslides(self):
        """
        4. Test multiple nearby landslides:
           - all qualifying inventory points are counted
        """
        # 3 points within ~100m-300m, 1 point 2km away
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [91.8605, 25.4200]},
            },
            {
                "type": "Feature",
                "properties": {"id": 2},
                "geometry": {"type": "Point", "coordinates": [91.8615, 25.4205]},
            },
            {
                "type": "Feature",
                "properties": {"id": 3},
                "geometry": {"type": "Point", "coordinates": [91.8595, 25.4195]},
            },
            {
                "type": "Feature",
                "properties": {"id": 4},
                "geometry": {"type": "Point", "coordinates": [91.8800, 25.4200]},  # ~2km away
            },
        ]
        indices = SpatialEnrichmentService.build_spatial_indices(inv_features, [])

        road = self._create_infra(
            "Multi Landslide Road",
            geom=LineString([(91.8600, 25.4190), (91.8600, 25.4210)]),
        )

        SpatialEnrichmentService.enrich_segment(road, indices, threshold_m=500.0)

        self.assertEqual(road.landslide_nearby_count, 3)
        self.assertEqual(road.historical_landslide_count, 3)
        self.assertIsNotNone(road.landslide_nearest_distance_m)
        self.assertLess(road.landslide_nearest_distance_m, 100.0)

    def test_crs_transformation_accuracy(self):
        """
        5. Test CRS transformation accuracy:
           - validate EPSG:4326 -> EPSG:32646
           - compare against known/reference metric coordinates or distances with reasonable tolerance
        """
        transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32646", always_xy=True)

        # 0.001 degree of latitude in East Khasi Hills (approx Lat 25.42, Lng 91.86)
        # 1 deg lat is approximately 110.8 km = 110,800 m.
        # 0.001 deg lat is approximately 110.8 m.
        p1_x, p1_y = transformer.transform(91.8600, 25.4200)
        p2_x, p2_y = transformer.transform(91.8600, 25.4210)

        calculated_dist = math.hypot(p2_x - p1_x, p2_y - p1_y)
        self.assertAlmostEqual(calculated_dist, 110.8, delta=1.5)

        # Confirm that UTM Zone 46N easting and northing are valid metric coordinates
        # Easting should be around 385,000 m; Northing around 2,812,000 m
        self.assertGreater(p1_x, 300000.0)
        self.assertLess(p1_x, 500000.0)
        self.assertGreater(p1_y, 2700000.0)
        self.assertLess(p1_y, 2900000.0)

    def test_missing_and_invalid_geometry(self):
        """
        6. Test missing and invalid geometry:
           - None
           - empty geometry
           - invalid/unusable geometry
           - empty inventory
           - empty susceptibility dataset
        """
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [91.8600, 25.4200]},
            }
        ]
        susc_features = [
            {
                "type": "Feature",
                "properties": {"id": "S1", "susceptibility_class": "High"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.85, 25.41], [91.87, 25.41], [91.87, 25.43], [91.85, 25.43], [91.85, 25.41]]],
                },
            }
        ]
        indices = SpatialEnrichmentService.build_spatial_indices(inv_features, susc_features)

        # None geometry
        road_none = self._create_infra("None Geom Road")
        road_none.geom = None
        SpatialEnrichmentService.enrich_segment(road_none, indices)
        self.assertFalse(road_none.landslide_zone_member)
        self.assertEqual(road_none.landslide_susceptibility, HazardLevel.LOW)
        self.assertIsNone(road_none.landslide_nearest_distance_m)
        self.assertEqual(road_none.landslide_nearby_count, 0)
        self.assertEqual(road_none.historical_landslide_count, 0)

        # Empty geometry
        road_empty = self._create_infra("Empty Geom Road")
        road_empty.geom = LineString([])
        SpatialEnrichmentService.enrich_segment(road_empty, indices)
        self.assertFalse(road_empty.landslide_zone_member)
        self.assertEqual(road_empty.landslide_susceptibility, HazardLevel.LOW)
        self.assertIsNone(road_empty.landslide_nearest_distance_m)
        self.assertEqual(road_empty.landslide_nearby_count, 0)

        # Empty datasets
        empty_indices = SpatialEnrichmentService.build_spatial_indices([], [])
        valid_road = self._create_infra(
            "Valid Road With Empty Data",
            geom=LineString([(91.855, 25.415), (91.865, 25.425)]),
        )
        SpatialEnrichmentService.enrich_segment(valid_road, empty_indices)
        self.assertFalse(valid_road.landslide_zone_member)
        self.assertEqual(valid_road.landslide_susceptibility, HazardLevel.LOW)
        self.assertIsNone(valid_road.landslide_nearest_distance_m)
        self.assertEqual(valid_road.landslide_nearby_count, 0)
        self.assertEqual(valid_road.historical_landslide_count, 0)

    def test_repeated_enrichment_deterministic(self):
        """
        7. Test repeated enrichment is deterministic:
           - run enrichment twice
           - derived values remain identical
           - nearby count never accumulates (e.g. 2 remains 2, never becomes 4)
        """
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [91.8605, 25.4200]},
            },
            {
                "type": "Feature",
                "properties": {"id": 2},
                "geometry": {"type": "Point", "coordinates": [91.8615, 25.4205]},
            },
        ]
        susc_features = [
            {
                "type": "Feature",
                "properties": {"id": "S1", "susceptibility_class": "High"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.85, 25.41], [91.87, 25.41], [91.87, 25.43], [91.85, 25.43], [91.85, 25.41]]],
                },
            }
        ]
        indices = SpatialEnrichmentService.build_spatial_indices(inv_features, susc_features)

        road = self._create_infra(
            "Deterministic Road",
            geom=LineString([(91.8600, 25.4190), (91.8600, 25.4210)]),
        )

        # Run 1
        SpatialEnrichmentService.enrich_segment(road, indices, threshold_m=500.0)
        first_member = road.landslide_zone_member
        first_susc = road.landslide_susceptibility
        first_dist = road.landslide_nearest_distance_m
        first_count = road.landslide_nearby_count
        first_hist = road.historical_landslide_count

        self.assertEqual(first_count, 2)
        self.assertEqual(first_hist, 2)

        # Run 2 on same instance
        SpatialEnrichmentService.enrich_segment(road, indices, threshold_m=500.0)

        self.assertEqual(road.landslide_zone_member, first_member)
        self.assertEqual(road.landslide_susceptibility, first_susc)
        self.assertEqual(road.landslide_nearest_distance_m, first_dist)
        self.assertEqual(road.landslide_nearby_count, first_count)
        self.assertEqual(road.historical_landslide_count, first_hist)

    def test_historical_landslide_count_matches_nearby_count(self):
        """
        8. Test that historical_landslide_count explicitly matches landslide_nearby_count:
           - verify the backward-compatibility invariant across multiple roads
        """
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [91.8600, 25.4200]},
            }
        ]
        indices = SpatialEnrichmentService.build_spatial_indices(inv_features, [])

        road_near = self._create_infra(
            "Road Near",
            geom=LineString([(91.8605, 25.4195), (91.8605, 25.4205)]),
        )
        road_far = self._create_infra(
            "Road Far",
            geom=LineString([(91.7000, 25.2000), (91.7100, 25.2100)]),
        )

        SpatialEnrichmentService.enrich_segment(road_near, indices, threshold_m=500.0)
        SpatialEnrichmentService.enrich_segment(road_far, indices, threshold_m=500.0)

        self.assertEqual(road_near.historical_landslide_count, road_near.landslide_nearby_count)
        self.assertEqual(road_far.historical_landslide_count, road_far.landslide_nearby_count)
        self.assertEqual(road_near.historical_landslide_count, 1)
        self.assertEqual(road_far.historical_landslide_count, 0)

    def test_highest_susceptibility_zone_wins(self):
        """
        9. Test highest susceptibility zone wins:
           - road intersects multiple susceptibility categories
           - High wins over Moderate/Medium and Low
        """
        susc_features = [
            {
                "type": "Feature",
                "properties": {"id": "S_LOW", "susceptibility_class": "Low"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.850, 25.410], [91.870, 25.410], [91.870, 25.430], [91.850, 25.430], [91.850, 25.410]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"id": "S_MOD", "susceptibility_class": "Moderate"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.865, 25.410], [91.885, 25.410], [91.885, 25.430], [91.865, 25.430], [91.865, 25.410]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"id": "S_HIGH", "susceptibility_class": "High"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.880, 25.410], [91.900, 25.410], [91.900, 25.430], [91.880, 25.430], [91.880, 25.410]]],
                },
            },
        ]
        indices = SpatialEnrichmentService.build_spatial_indices([], susc_features)

        # Road crossing Low and Moderate (no High)
        road_low_mod = self._create_infra(
            "Low-Mod Road",
            geom=LineString([(91.855, 25.420), (91.875, 25.420)]),
        )
        SpatialEnrichmentService.enrich_segment(road_low_mod, indices)
        self.assertTrue(road_low_mod.landslide_zone_member)
        self.assertEqual(road_low_mod.landslide_susceptibility, HazardLevel.MEDIUM)

        # Road crossing Moderate and High
        road_mod_high = self._create_infra(
            "Mod-High Road",
            geom=LineString([(91.870, 25.420), (91.890, 25.420)]),
        )
        SpatialEnrichmentService.enrich_segment(road_mod_high, indices)
        self.assertTrue(road_mod_high.landslide_zone_member)
        self.assertEqual(road_mod_high.landslide_susceptibility, HazardLevel.HIGH)

        # Road crossing all three (Low, Moderate, High)
        road_all = self._create_infra(
            "All-Zones Road",
            geom=LineString([(91.855, 25.420), (91.895, 25.420)]),
        )
        SpatialEnrichmentService.enrich_segment(road_all, indices)
        self.assertTrue(road_all.landslide_zone_member)
        self.assertEqual(road_all.landslide_susceptibility, HazardLevel.HIGH)

    def test_empty_inventory_semantics(self):
        """
        10. Test empty inventory semantics:
            - nearest distance is NULL
            - nearby count is 0
            - historical count is 0
        """
        indices = SpatialEnrichmentService.build_spatial_indices([], [])

        road = self._create_infra(
            "Road In Empty Inventory",
            geom=LineString([(91.850, 25.420), (91.860, 25.420)]),
        )

        SpatialEnrichmentService.enrich_segment(road, indices)

        self.assertIsNone(road.landslide_nearest_distance_m)
        self.assertEqual(road.landslide_nearby_count, 0)
        self.assertEqual(road.historical_landslide_count, 0)

    def test_enrich_all_batch_and_summary_statistics(self):
        """
        Verify enrich_all processes queryset, returns accurate summary statistics,
        and persists results correctly using bulk_update.
        """
        inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [91.8600, 25.4200]},
            }
        ]
        susc_features = [
            {
                "type": "Feature",
                "properties": {"id": "S1", "susceptibility_class": "High"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.85, 25.41], [91.87, 25.41], [91.87, 25.43], [91.85, 25.43], [91.85, 25.41]]],
                },
            }
        ]

        # Create two roads: one near and inside zone, one far and outside zone
        road1 = self._create_infra("Road 1", geom=LineString([(91.855, 25.420), (91.865, 25.420)]))
        road2 = self._create_infra("Road 2", geom=LineString([(91.700, 25.200), (91.710, 25.200)]))

        qs = Infrastructure.objects.filter(pk__in=[road1.pk, road2.pk])

        import tempfile
        import json

        with tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f_inv, \
             tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False) as f_susc:
            json.dump({"type": "FeatureCollection", "features": inv_features}, f_inv)
            json.dump({"type": "FeatureCollection", "features": susc_features}, f_susc)
            f_inv_path = f_inv.name
            f_susc_path = f_susc.name

        summary = SpatialEnrichmentService.enrich_all(
            queryset=qs,
            inventory_path=f_inv_path,
            susceptibility_path=f_susc_path,
            threshold_m=500.0,
            persist=True,
        )

        self.assertEqual(summary['total_processed'], 2)
        self.assertEqual(summary['intersecting_zones'], 1)
        self.assertEqual(summary['with_nearby_landslides'], 1)
        self.assertEqual(summary['zero_nearby_landslides'], 1)
        self.assertIsNotNone(summary['min_nearest_distance_m'])
        self.assertIsNotNone(summary['max_nearest_distance_m'])
        self.assertIsNotNone(summary['avg_nearest_distance_m'])

        # Verify persisted values in database
        road1.refresh_from_db()
        road2.refresh_from_db()

        self.assertTrue(road1.landslide_zone_member)
        self.assertEqual(road1.landslide_susceptibility, HazardLevel.HIGH)
        self.assertEqual(road1.landslide_nearby_count, 1)

        self.assertFalse(road2.landslide_zone_member)
        self.assertEqual(road2.landslide_nearby_count, 0)


class SpatialEnrichmentOperationalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        poly = Polygon(((91.70, 25.20), (92.10, 25.20), (92.10, 25.60), (91.70, 25.60), (91.70, 25.20)))
        cls.district = District.objects.create(
            name="Command Test District",
            state="Meghalaya",
            accessibility_score=8.0,
            geom=MultiPolygon(poly),
        )

    def setUp(self):
        self.inv_features = [
            {
                "type": "Feature",
                "properties": {"id": 1, "name": "Slide 1"},
                "geometry": {"type": "Point", "coordinates": [91.86000, 25.42000]},
            }
        ]
        self.susc_features = [
            {
                "type": "Feature",
                "properties": {"id": "S1", "susceptibility_class": "High"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[91.85, 25.41], [91.87, 25.41], [91.87, 25.43], [91.85, 25.43], [91.85, 25.41]]],
                },
            }
        ]

    def _write_geojson(self, data):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False)
        json.dump(data, f)
        f.flush()
        f.close()
        return f.name

    def _create_infra(self, name: str, geom=None, **kwargs) -> Infrastructure:
        defaults = {
            'district': self.district,
            'name': name,
            'infra_type': InfrastructureType.ROAD,
            'road_classification': RoadClassification.NATIONAL_HIGHWAY,
            'start_node': 2001,
            'end_node': 2002,
            'length_km': 5.0,
            'geom': geom or LineString([(91.855, 25.420), (91.865, 25.420)]),
        }
        defaults.update(kwargs)
        return Infrastructure.objects.create(**defaults)

    def test_management_command_dry_run(self):
        """Dry-run must output metrics but not modify database rows."""
        road = self._create_infra("DryRun Road")
        inv_path = self._write_geojson({"type": "FeatureCollection", "features": self.inv_features})
        susc_path = self._write_geojson({"type": "FeatureCollection", "features": self.susc_features})

        out = StringIO()
        call_command(
            'enrich_landslide_spatial',
            inventory=inv_path,
            susceptibility=susc_path,
            threshold=500.0,
            dry_run=True,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("DRY-RUN", output)
        self.assertIn("Total Candidate Roads:", output)
        self.assertIn("Enriched Count:", output)
        self.assertIn("Updated Count:                             0", output)
        self.assertIn("Roads with Nearest Landslide <= Threshold:", output)
        self.assertIn("Roads with Nearest Landslide > Threshold:", output)

        road.refresh_from_db()
        self.assertFalse(road.landslide_zone_member)
        self.assertIsNone(road.landslide_nearest_distance_m)
        self.assertEqual(road.landslide_nearby_count, 0)

    def test_management_command_live_persistence(self):
        """Live run must persist computed enrichment to database and report metrics."""
        road = self._create_infra("Live Road")
        inv_path = self._write_geojson({"type": "FeatureCollection", "features": self.inv_features})
        susc_path = self._write_geojson({"type": "FeatureCollection", "features": self.susc_features})

        out = StringIO()
        call_command(
            'enrich_landslide_spatial',
            inventory=inv_path,
            susceptibility=susc_path,
            threshold=500.0,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("SUCCESS", output)
        self.assertIn("Total Candidate Roads:", output)
        self.assertIn("Enriched Count:                            1", output)
        self.assertIn("Updated Count:                             1", output)
        self.assertIn("Roads with Nearest Landslide <= Threshold: 1", output)

        road.refresh_from_db()
        self.assertTrue(road.landslide_zone_member)
        self.assertEqual(road.landslide_susceptibility, HazardLevel.HIGH)
        self.assertIsNotNone(road.landslide_nearest_distance_m)
        self.assertEqual(road.landslide_nearby_count, 1)
        self.assertEqual(road.historical_landslide_count, 1)

    def test_management_command_custom_arguments(self):
        """Custom threshold, metric-srid, and paths must be respected."""
        road = self._create_infra("Custom Arg Road", geom=LineString([(91.861, 25.419), (91.861, 25.421)]))
        inv_path = self._write_geojson({"type": "FeatureCollection", "features": self.inv_features})
        susc_path = self._write_geojson({"type": "FeatureCollection", "features": []})

        out = StringIO()
        call_command(
            'enrich_landslide_spatial',
            inventory=inv_path,
            susceptibility=susc_path,
            threshold=50.0,
            metric_srid=32646,
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("Proximity Threshold:     50.0 m", output)
        self.assertIn("Projected Metric SRID:   EPSG:32646", output)
        self.assertIn("Roads with Nearest Landslide <= Threshold: 0", output)
        self.assertIn("Roads with Nearest Landslide > Threshold:  1", output)

        road.refresh_from_db()
        self.assertEqual(road.landslide_nearby_count, 0)
        self.assertGreater(road.landslide_nearest_distance_m, 50.0)

    def test_management_command_missing_file_raises_command_error(self):
        """Missing inventory or susceptibility file must raise CommandError."""
        with self.assertRaises(CommandError):
            call_command('enrich_landslide_spatial', inventory='/non/existent/inventory.geojson')

    def test_management_command_invalid_json_raises_command_error(self):
        """Corrupt or non-JSON GeoJSON file must raise CommandError."""
        bad_file = tempfile.NamedTemporaryFile(mode='w', suffix='.geojson', delete=False)
        bad_file.write("NOT VALID JSON")
        bad_file.close()

        with self.assertRaises(CommandError):
            call_command('enrich_landslide_spatial', inventory=bad_file.name)

    def test_serializer_exposes_enrichment_fields(self):
        """InfrastructureSerializer must expose all spatial enrichment attributes."""
        road = self._create_infra(
            "Serialized Road",
            landslide_zone_member=True,
            landslide_susceptibility=HazardLevel.HIGH,
            landslide_nearest_distance_m=124.56,
            landslide_nearby_count=2,
            historical_landslide_count=2,
        )

        serializer = InfrastructureSerializer(road)
        data = serializer.data

        self.assertIn('landslide_nearest_distance_m', data)
        self.assertIn('landslide_nearby_count', data)
        self.assertIn('landslide_zone_member', data)
        self.assertIn('landslide_susceptibility', data)
        self.assertIn('historical_landslide_count', data)

        self.assertEqual(data['landslide_nearest_distance_m'], 124.56)
        self.assertEqual(data['landslide_nearby_count'], 2)
        self.assertTrue(data['landslide_zone_member'])
        self.assertEqual(data['landslide_susceptibility'], 'high')
        self.assertEqual(data['historical_landslide_count'], 2)

    def test_serializer_handles_null_nearest_distance(self):
        """InfrastructureSerializer must serialize null nearest distance as None/null."""
        road = self._create_infra(
            "Null Distance Road",
            landslide_nearest_distance_m=None,
            landslide_nearby_count=0,
            landslide_zone_member=False,
        )

        serializer = InfrastructureSerializer(road)
        data = serializer.data

        self.assertIsNone(data['landslide_nearest_distance_m'])
        self.assertEqual(data['landslide_nearby_count'], 0)
        self.assertFalse(data['landslide_zone_member'])

    def test_serializer_backward_compatibility(self):
        """Existing serializer fields and structure must remain intact."""
        road = self._create_infra("Legacy Contract Road")
        serializer = InfrastructureSerializer(road)
        data = serializer.data

        expected_fields = [
            'id', 'name', 'district', 'district_name', 'state',
            'infra_type', 'road_classification', 'start_node', 'end_node',
            'length_km', 'base_speed_kmh', 'base_travel_time_min',
            'status', 'condition', 'flood_hazard_zone', 'recent_rainfall_mm',
            'weather_warning', 'risk_score', 'disruption_probability',
            'risk_level', 'top_factors', 'last_assessed_at', 'coordinates',
        ]
        for f in expected_fields:
            self.assertIn(f, data, f"Missing expected field {f} in serialized Infrastructure")

        self.assertEqual(data['name'], "Legacy Contract Road")
        self.assertEqual(data['district_name'], "Command Test District")
        self.assertEqual(data['state'], "Meghalaya")
        self.assertIsInstance(data['coordinates'], list)


