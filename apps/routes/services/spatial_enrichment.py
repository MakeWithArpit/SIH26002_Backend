"""
Spatial Enrichment Service — Static Landslide Hazard Enrichment Engine.

Matches road Infrastructure geometries against:
1. GSI Historical Landslide Inventory (Points) -> distance to nearest and count within threshold.
2. GSI Landslide Susceptibility Zones (Polygons) -> zone membership and category.

Key guarantees:
- Pure static data enrichment (NO risk scores, rainfall, or route modifications).
- Calculations performed in projected metric CRS (EPSG:32646 / UTM Zone 46N) for meter-accurate distances.
- Uses Shapely STRtree spatial indexes for O(log N) candidate queries rather than N×M pairwise checks.
- Safely handles MultiLineString, missing/empty geometry, and empty datasets.
- Strictly idempotent: recalculates from source, never accumulates counts.
- Maintains invariant: historical_landslide_count == landslide_nearby_count.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pyproj
import shapely
import shapely.ops
import shapely.wkb
from django.conf import settings
from django.db import transaction
from shapely.geometry import shape, Point, MultiPoint, Polygon, MultiPolygon, LineString, MultiLineString
from shapely.strtree import STRtree

from apps.routes.models import HazardLevel, Infrastructure

logger = logging.getLogger(__name__)


# Susceptibility severity ordering: High > Moderate/Medium > Low
SEVERITY_ORDER = {
    HazardLevel.HIGH: 3,
    HazardLevel.MEDIUM: 2,
    HazardLevel.LOW: 1,
}


class SpatialEnrichmentService:
    """
    Reusable service for matching road Infrastructure geometries
    against GSI landslide inventory points and susceptibility polygons.
    """

    @classmethod
    def resolve_dataset_path(cls, file_path: Union[str, Path, None], default_setting_key: str) -> Path:
        """
        Resolve dataset path, preferring explicit argument, then Django setting.
        Relative paths are resolved relative to settings.BASE_DIR.
        """
        if file_path is None:
            raw_path = getattr(settings, default_setting_key, None)
        else:
            raw_path = file_path

        if not raw_path:
            raise ValueError(f"No path specified and setting '{default_setting_key}' is not configured.")

        path_obj = Path(raw_path)
        if not path_obj.is_absolute():
            base_dir = getattr(settings, 'BASE_DIR', Path.cwd())
            path_obj = (Path(base_dir) / path_obj).resolve()

        return path_obj

    @classmethod
    def load_datasets(
        cls,
        inventory_path: Union[str, Path, None] = None,
        susceptibility_path: Union[str, Path, None] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Load and validate GSI GeoJSON files from disk.
        Returns (inventory_features, susceptibility_features).

        Fails clearly if files are missing or unreadable, but safely supports
        empty datasets (features list is empty).
        """
        resolved_inv = cls.resolve_dataset_path(inventory_path, 'LANDSLIDE_INVENTORY_PATH')
        resolved_susc = cls.resolve_dataset_path(susceptibility_path, 'LANDSLIDE_SUSCEPTIBILITY_PATH')

        # Fallback check: if data/geospatial/gsi doesn't exist, check data/geospatial/bhuvan
        if not resolved_inv.exists():
            alt_inv = Path(str(resolved_inv).replace(r'geospatial\gsi', r'geospatial\bhuvan').replace('geospatial/gsi', 'geospatial/bhuvan'))
            if alt_inv.exists():
                resolved_inv = alt_inv

        if not resolved_susc.exists():
            alt_susc = Path(str(resolved_susc).replace(r'geospatial\gsi', r'geospatial\bhuvan').replace('geospatial/gsi', 'geospatial/bhuvan'))
            if alt_susc.exists():
                resolved_susc = alt_susc

        if not resolved_inv.exists():
            raise FileNotFoundError(f"Landslide inventory dataset not found at: {resolved_inv}")
        if not resolved_susc.exists():
            raise FileNotFoundError(f"Landslide susceptibility dataset not found at: {resolved_susc}")

        try:
            with open(resolved_inv, 'r', encoding='utf-8') as f:
                inv_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to read/decode inventory GeoJSON at {resolved_inv}: {e}") from e

        try:
            with open(resolved_susc, 'r', encoding='utf-8') as f:
                susc_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to read/decode susceptibility GeoJSON at {resolved_susc}: {e}") from e

        inv_features = inv_data.get('features', []) if isinstance(inv_data, dict) else []
        susc_features = susc_data.get('features', []) if isinstance(susc_data, dict) else []

        logger.info(
            "Loaded datasets successfully: %d inventory features from %s, %d susceptibility features from %s",
            len(inv_features),
            resolved_inv.name,
            len(susc_features),
            resolved_susc.name,
        )

        return inv_features, susc_features

    @classmethod
    def map_susceptibility_class(cls, properties: Dict[str, Any]) -> str:
        """
        Inspect feature properties to extract and normalize the susceptibility category.
        Maps raw values to project's existing HazardLevel choices:
        - 'High' -> HazardLevel.HIGH ('high')
        - 'Moderate' / 'Medium' -> HazardLevel.MEDIUM ('medium')
        - 'Low' -> HazardLevel.LOW ('low')
        """
        if not properties:
            return HazardLevel.LOW

        # Inspect candidate property keys without assuming a single fixed name
        raw_val = None
        for key in ('susceptibility_class', 'susceptibility', 'class', 'hazard_level', 'hazard', 'category', 'level'):
            if key in properties and properties[key] is not None:
                raw_val = str(properties[key]).strip().lower()
                break

        if not raw_val:
            return HazardLevel.LOW

        if raw_val in ('high', 'very high', 'vh', 'h'):
            return HazardLevel.HIGH
        elif raw_val in ('moderate', 'medium', 'mod', 'm'):
            return HazardLevel.MEDIUM
        elif raw_val in ('low', 'very low', 'vl', 'l'):
            return HazardLevel.LOW
        return HazardLevel.LOW

    @classmethod
    def build_spatial_indices(
        cls,
        inventory_features: List[Dict[str, Any]],
        susceptibility_features: List[Dict[str, Any]],
        metric_srid: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Transform features into metric CRS (EPSG:32646) and build Shapely STRtrees.
        Returns a context dictionary containing the trees, projected geometries,
        and projection transformer.
        """
        if metric_srid is None:
            metric_srid = getattr(settings, 'LANDSLIDE_METRIC_SRID', 32646)

        transformer = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{metric_srid}", always_xy=True)

        # 1. Project Inventory Points
        projected_points = []
        inventory_records = []
        skipped_inventory = 0

        for feat in inventory_features:
            geom_dict = feat.get('geometry')
            if not geom_dict:
                skipped_inventory += 1
                continue
            try:
                geom_4326 = shape(geom_dict)
                if geom_4326.is_empty:
                    skipped_inventory += 1
                    continue
                # Transform (lng, lat) -> (X_meters, Y_meters)
                geom_m = shapely.ops.transform(transformer.transform, geom_4326)
                projected_points.append(geom_m)
                inventory_records.append(feat.get('properties', {}))
            except Exception as e:
                logger.warning("Skipping invalid inventory feature: %s", e)
                skipped_inventory += 1

        inventory_tree = STRtree(projected_points) if projected_points else STRtree([])

        # 2. Project Susceptibility Polygons
        projected_polygons = []
        susceptibility_records = []
        skipped_susceptibility = 0

        for feat in susceptibility_features:
            geom_dict = feat.get('geometry')
            if not geom_dict:
                skipped_susceptibility += 1
                continue
            try:
                geom_4326 = shape(geom_dict)
                if geom_4326.is_empty:
                    skipped_susceptibility += 1
                    continue
                if not geom_4326.is_valid:
                    geom_4326 = geom_4326.buffer(0)
                geom_m = shapely.ops.transform(transformer.transform, geom_4326)
                hazard_class = cls.map_susceptibility_class(feat.get('properties', {}))
                projected_polygons.append(geom_m)
                susceptibility_records.append({
                    'properties': feat.get('properties', {}),
                    'hazard_class': hazard_class,
                })
            except Exception as e:
                logger.warning("Skipping invalid susceptibility feature: %s", e)
                skipped_susceptibility += 1

        susceptibility_tree = STRtree(projected_polygons) if projected_polygons else STRtree([])

        return {
            'transformer': transformer,
            'metric_srid': metric_srid,
            'inventory_tree': inventory_tree,
            'inventory_points': projected_points,
            'inventory_records': inventory_records,
            'susceptibility_tree': susceptibility_tree,
            'susceptibility_polygons': projected_polygons,
            'susceptibility_records': susceptibility_records,
            'skipped_inventory': skipped_inventory,
            'skipped_susceptibility': skipped_susceptibility,
        }

    @classmethod
    def enrich_segment(
        cls,
        infra: Infrastructure,
        spatial_indices: Dict[str, Any],
        threshold_m: Optional[float] = None,
    ) -> Infrastructure:
        """
        Calculate and assign static geospatial enrichment attributes to a single Infrastructure instance.
        Never mutates the underlying stored Infrastructure geometry.

        Enrichment attributes assigned:
        - landslide_zone_member: bool
        - landslide_susceptibility: HazardLevel choice ('high', 'medium', 'low')
        - landslide_nearest_distance_m: Optional[float]
        - landslide_nearby_count: int
        - historical_landslide_count: int (synced with landslide_nearby_count)
        """
        if threshold_m is None:
            threshold_m = float(getattr(settings, 'LANDSLIDE_PROXIMITY_THRESHOLD_M', 500.0))

        inventory_points = spatial_indices['inventory_points']
        inventory_tree = spatial_indices['inventory_tree']
        susceptibility_polygons = spatial_indices['susceptibility_polygons']
        susceptibility_records = spatial_indices['susceptibility_records']
        susceptibility_tree = spatial_indices['susceptibility_tree']
        transformer = spatial_indices['transformer']

        # Missing or empty road geometry handling
        if not infra.geom or infra.geom.empty:
            infra.landslide_zone_member = False
            infra.landslide_susceptibility = HazardLevel.LOW
            infra.landslide_nearest_distance_m = None
            infra.landslide_nearby_count = 0
            infra.historical_landslide_count = 0
            return infra

        # Convert GeoDjango geometry safely to Shapely
        try:
            road_4326 = shapely.wkb.loads(bytes(infra.geom.wkb))
        except Exception as e:
            logger.warning("Failed to load WKB for Infrastructure #%s: %s", infra.pk, e)
            infra.landslide_zone_member = False
            infra.landslide_susceptibility = HazardLevel.LOW
            infra.landslide_nearest_distance_m = None
            infra.landslide_nearby_count = 0
            infra.historical_landslide_count = 0
            return infra

        if road_4326.is_empty:
            infra.landslide_zone_member = False
            infra.landslide_susceptibility = HazardLevel.LOW
            infra.landslide_nearest_distance_m = None
            infra.landslide_nearby_count = 0
            infra.historical_landslide_count = 0
            return infra

        # Transform road geometry to metric CRS for metric distance/buffer calculations
        try:
            road_metric = shapely.ops.transform(transformer.transform, road_4326)
            if not road_metric.is_valid:
                road_metric = road_metric.buffer(0)
        except Exception as e:
            logger.warning("Failed to project road geometry for Infrastructure #%s: %s", infra.pk, e)
            infra.landslide_zone_member = False
            infra.landslide_susceptibility = HazardLevel.LOW
            infra.landslide_nearest_distance_m = None
            infra.landslide_nearby_count = 0
            infra.historical_landslide_count = 0
            return infra

        # ── 1. Susceptibility Zone Matching ──────────────────────────────────
        if susceptibility_polygons:
            intersecting_indices = susceptibility_tree.query(road_metric, predicate='intersects')
            if len(intersecting_indices) > 0:
                infra.landslide_zone_member = True
                # Find highest severity among intersecting polygons (High > Moderate/Medium > Low)
                intersecting_classes = [
                    susceptibility_records[idx]['hazard_class'] for idx in intersecting_indices
                ]
                highest_class = max(
                    intersecting_classes,
                    key=lambda c: SEVERITY_ORDER.get(c, 0),
                    default=HazardLevel.LOW,
                )
                infra.landslide_susceptibility = highest_class
            else:
                infra.landslide_zone_member = False
                infra.landslide_susceptibility = HazardLevel.LOW
        else:
            infra.landslide_zone_member = False
            infra.landslide_susceptibility = HazardLevel.LOW

        # ── 2. Historical Landslide Proximity & Count ────────────────────────
        if inventory_points:
            # Nearest historical landslide distance in meters
            nearest_idx = inventory_tree.nearest(road_metric)
            if nearest_idx is not None:
                nearest_geom = inventory_points[nearest_idx]
                exact_dist_m = road_metric.distance(nearest_geom)
                infra.landslide_nearest_distance_m = round(float(exact_dist_m), 2)
            else:
                infra.landslide_nearest_distance_m = None

            # Number of historical landslide records within configured proximity threshold
            road_buffer = road_metric.buffer(threshold_m)
            candidates = inventory_tree.query(road_buffer)
            exact_count = sum(
                1 for idx in candidates if road_metric.distance(inventory_points[idx]) <= threshold_m
            )
            infra.landslide_nearby_count = exact_count
            infra.historical_landslide_count = exact_count
        else:
            infra.landslide_nearest_distance_m = None
            infra.landslide_nearby_count = 0
            infra.historical_landslide_count = 0

        return infra

    @classmethod
    def enrich_all(
        cls,
        queryset=None,
        threshold_m: Optional[float] = None,
        metric_srid: Optional[int] = None,
        inventory_path: Union[str, Path, None] = None,
        susceptibility_path: Union[str, Path, None] = None,
        persist: bool = True,
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        """
        Execute static spatial enrichment across Infrastructure segments.

        - Recomputes attributes strictly from the source datasets (idempotent).
        - Avoids N×M processing using prebuilt Shapely STRtree indexes.
        - Persists in batches using bulk_update within transaction.atomic().
        - Returns comprehensive summary statistics.
        """
        if queryset is None:
            queryset = Infrastructure.objects.all()

        if threshold_m is None:
            threshold_m = float(getattr(settings, 'LANDSLIDE_PROXIMITY_THRESHOLD_M', 500.0))

        inv_features, susc_features = cls.load_datasets(
            inventory_path=inventory_path,
            susceptibility_path=susceptibility_path,
        )

        indices = cls.build_spatial_indices(
            inventory_features=inv_features,
            susceptibility_features=susc_features,
            metric_srid=metric_srid,
        )

        total_processed = 0
        intersecting_zones = 0
        with_nearby_landslides = 0
        zero_nearby_landslides = 0
        affected_segments = 0
        all_nearest_distances = []
        roads_within_threshold = 0
        roads_outside_threshold = 0
        unmatched_roads_count = 0
        total_nearby_associations = 0
        invalid_skipped_count = 0
        susceptibility_distribution = {
            HazardLevel.HIGH: 0,
            HazardLevel.MEDIUM: 0,
            HazardLevel.LOW: 0,
        }

        records_to_update = []

        for infra in queryset.iterator():
            if not infra.geom or infra.geom.empty:
                invalid_skipped_count += 1

            cls.enrich_segment(infra, indices, threshold_m=threshold_m)

            total_processed += 1
            if infra.landslide_zone_member:
                intersecting_zones += 1

            if infra.landslide_nearby_count > 0:
                with_nearby_landslides += 1
            else:
                zero_nearby_landslides += 1

            if infra.landslide_zone_member or infra.landslide_nearby_count > 0:
                affected_segments += 1

            susc_val = infra.landslide_susceptibility or HazardLevel.LOW
            susceptibility_distribution[susc_val] = (
                susceptibility_distribution.get(susc_val, 0) + 1
            )

            total_nearby_associations += infra.landslide_nearby_count

            if infra.landslide_nearest_distance_m is not None:
                all_nearest_distances.append(infra.landslide_nearest_distance_m)
                if infra.landslide_nearest_distance_m <= threshold_m:
                    roads_within_threshold += 1
                else:
                    roads_outside_threshold += 1
            else:
                unmatched_roads_count += 1

            if persist:
                records_to_update.append(infra)
                if len(records_to_update) >= batch_size:
                    with transaction.atomic():
                        Infrastructure.objects.bulk_update(
                            records_to_update,
                            [
                                'landslide_zone_member',
                                'landslide_susceptibility',
                                'landslide_nearest_distance_m',
                                'landslide_nearby_count',
                                'historical_landslide_count',
                            ],
                        )
                    records_to_update.clear()

        # Flush remaining updates
        if persist and records_to_update:
            with transaction.atomic():
                Infrastructure.objects.bulk_update(
                    records_to_update,
                    [
                        'landslide_zone_member',
                        'landslide_susceptibility',
                        'landslide_nearest_distance_m',
                        'landslide_nearby_count',
                        'historical_landslide_count',
                    ],
                )
            records_to_update.clear()

        min_dist = min(all_nearest_distances) if all_nearest_distances else None
        max_dist = max(all_nearest_distances) if all_nearest_distances else None
        avg_dist = (
            round(sum(all_nearest_distances) / len(all_nearest_distances), 2)
            if all_nearest_distances
            else None
        )

        summary = {
            'total_processed': total_processed,
            'affected_segments': affected_segments,
            'updated_count': total_processed if persist else 0,
            'intersecting_zones': intersecting_zones,
            'with_nearby_landslides': with_nearby_landslides,
            'zero_nearby_landslides': zero_nearby_landslides,
            'roads_within_threshold': roads_within_threshold,
            'roads_outside_threshold': roads_outside_threshold,
            'unmatched_roads_count': unmatched_roads_count,
            'min_nearest_distance_m': min_dist,
            'max_nearest_distance_m': max_dist,
            'avg_nearest_distance_m': avg_dist,
            'total_nearby_associations': total_nearby_associations,
            'susceptibility_distribution': susceptibility_distribution,
            'invalid_skipped_count': invalid_skipped_count,
            'threshold_m': threshold_m,
            'metric_srid': indices['metric_srid'],
        }

        logger.info(
            "Enrichment completed: %d segments processed (%d in zones, %d with nearby slides).",
            total_processed,
            intersecting_zones,
            with_nearby_landslides,
        )

        return summary

