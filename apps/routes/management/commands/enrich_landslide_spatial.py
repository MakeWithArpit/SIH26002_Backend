"""
Management command: enrich_landslide_spatial

Executes static landslide geospatial enrichment on Infrastructure segments:
- Determines susceptibility zone intersections and categories
- Computes metric distance to nearest historical landslide record
- Counts historical landslides within configurable proximity threshold
- Persists results (unless --dry-run is specified)
- Outputs comprehensive summary statistics
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from apps.routes.models import HazardLevel
from apps.routes.services.spatial_enrichment import SpatialEnrichmentService


class Command(BaseCommand):
    help = "Enrich Infrastructure road segments with static GSI landslide hazard attributes."

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold',
            type=float,
            default=None,
            help=(
                f"Proximity threshold in meters (default: {getattr(settings, 'LANDSLIDE_PROXIMITY_THRESHOLD_M', 500.0)}m)"
            ),
        )
        parser.add_argument(
            '--inventory',
            type=str,
            default=None,
            help="Optional filesystem path override for landslide inventory GeoJSON",
        )
        parser.add_argument(
            '--susceptibility',
            type=str,
            default=None,
            help="Optional filesystem path override for susceptibility GeoJSON",
        )
        parser.add_argument(
            '--metric-srid',
            type=int,
            default=None,
            help=f"Projected metric SRID (default: {getattr(settings, 'LANDSLIDE_METRIC_SRID', 32646)})",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help="Compute enrichment and display summary statistics without modifying database records",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        threshold = options['threshold']
        inventory_path = options['inventory']
        susceptibility_path = options['susceptibility']
        metric_srid = options['metric_srid']

        mode_str = "DRY-RUN (No DB changes)" if dry_run else "LIVE PERSISTENCE"
        self.stdout.write(self.style.NOTICE(f"\n=== Static Landslide Spatial Enrichment [{mode_str}] ==="))

        try:
            summary = SpatialEnrichmentService.enrich_all(
                threshold_m=threshold,
                metric_srid=metric_srid,
                inventory_path=inventory_path,
                susceptibility_path=susceptibility_path,
                persist=not dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            raise CommandError(str(e))
        except Exception as e:
            raise CommandError(f"Spatial enrichment failed: {e}")

        # Extract summary metrics
        total = summary['total_processed']
        affected = summary['affected_segments']
        updated = summary['updated_count']
        intersecting = summary['intersecting_zones']
        nearby = summary['with_nearby_landslides']
        within_thresh = summary['roads_within_threshold']
        outside_thresh = summary['roads_outside_threshold']
        skipped_unmatched = summary['unmatched_roads_count'] + summary['invalid_skipped_count']
        zero_nearby = summary['zero_nearby_landslides']
        total_assoc = summary['total_nearby_associations']
        susc_dist = summary.get('susceptibility_distribution', {})
        threshold_used = summary['threshold_m']
        srid_used = summary['metric_srid']

        min_dist_str = f"{summary['min_nearest_distance_m']:.2f} m" if summary['min_nearest_distance_m'] is not None else "N/A"
        max_dist_str = f"{summary['max_nearest_distance_m']:.2f} m" if summary['max_nearest_distance_m'] is not None else "N/A"
        avg_dist_str = f"{summary['avg_nearest_distance_m']:.2f} m" if summary['avg_nearest_distance_m'] is not None else "N/A"

        self.stdout.write("\nConfiguration:")
        self.stdout.write(f"  - Proximity Threshold:     {threshold_used} m")
        self.stdout.write(f"  - Projected Metric SRID:   EPSG:{srid_used}")

        self.stdout.write("\nProcessing Summary:")
        self.stdout.write(f"  - Total Candidate Roads:                     {total}")
        self.stdout.write(f"  - Enriched Count:                            {affected}")
        self.stdout.write(f"  - Updated Count:                             {updated}")
        self.stdout.write(f"  - Intersection Count (Susceptibility Zones): {intersecting}")
        self.stdout.write(f"  - Roads with Nearest Landslide <= Threshold: {within_thresh}")
        self.stdout.write(f"  - Roads with Nearest Landslide > Threshold:  {outside_thresh}")
        self.stdout.write(f"  - Skipped / Unmatched Roads:                 {skipped_unmatched}")
        self.stdout.write(f"  - Total Nearby Landslide Associations:       {total_assoc}")

        self.stdout.write("\nNearest Landslide Distance:")
        self.stdout.write(f"  - Minimum Distance:   {min_dist_str}")
        self.stdout.write(f"  - Maximum Distance:   {max_dist_str}")
        self.stdout.write(f"  - Average Distance:   {avg_dist_str}")

        self.stdout.write("\nSusceptibility Distribution:")
        self.stdout.write(f"  - High:       {susc_dist.get(HazardLevel.HIGH, 0)}")
        self.stdout.write(f"  - Moderate:   {susc_dist.get(HazardLevel.MEDIUM, 0)}")
        self.stdout.write(f"  - Low:        {susc_dist.get(HazardLevel.LOW, 0)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[DRY-RUN] Execution completed. No database rows were modified.\n"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] Successfully enriched and persisted {total} Infrastructure segments.\n"))
