"""
Management command: seed_dummy_data

Comprehensive dummy data seeder for SIH26002 Backend.
Creates 50+ records per model with realistic GIS coordinates for NER corridor.

Usage: python manage.py seed_dummy_data
"""
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import MultiPolygon, Polygon, LineString, Point
from django.contrib.auth.models import User
from django.utils import timezone

from apps.accounts.models import Profile, Role
from apps.routes.models import (
    District, Infrastructure, InfrastructureType, RoadClassification,
    HazardLevel, OperationalStatus, PhysicalCondition, RiskLevel,
    ConnectivityStatus, WeatherCondition, WeatherSnapshot
)
from apps.reports.models import IncidentReport, IncidentType, SeverityLevel, AnalysisStatus, ReportStatus
from apps.vehicles.models import Vehicle, VehicleType, LocationPing, Trip, TripStatus
from apps.routes.services.risk import RiskPredictionService
from apps.routes.services.routing.graph import RoadNetworkGraphService


class Command(BaseCommand):
    help = 'Seed comprehensive dummy data (50+ records per model) for NER logistics corridor'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('\n=== SEEDING COMPREHENSIVE DUMMY DATA ===\n'))
        
        # Skip clearing - just add new data
        
        # Seed in order of dependencies
        self.seed_users()
        self.seed_districts()
        self.seed_infrastructure()
        self.seed_weather()
        self.seed_vehicles()
        self.seed_location_pings()
        self.seed_trips()
        self.seed_incident_reports()
        
        # Rebuild graph cache
        RoadNetworkGraphService.clear_graph_cache()
        
        self.stdout.write(self.style.SUCCESS('\n=== DUMMY DATA SEEDING COMPLETE ==='))
        self.stdout.write(self.style.SUCCESS('Run: python manage.py seed_dummy_data'))
        self.stdout.write(self.style.SUCCESS('Login credentials saved to: projectInformation/DUMMY_DATA_CREDENTIALS.md\n'))

    def clear_existing_data(self):
        """Clear existing data to avoid duplicates"""
        self.stdout.write('Clearing existing data...')
        # Delete in correct order to respect foreign keys
        Trip.objects.all().delete()
        LocationPing.objects.all().delete()  # Before Vehicle
        Vehicle.objects.all().delete()
        IncidentReport.objects.all().delete()
        WeatherSnapshot.objects.all().delete()  # Before Infrastructure (references district)
        Infrastructure.objects.all().delete()
        District.objects.all().delete()  # After WeatherSnapshot
        Profile.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write(self.style.SUCCESS('  Existing data cleared.\n'))

    def seed_users(self):
        """Create 50+ users with different roles"""
        self.stdout.write(self.style.NOTICE('Seeding Users...'))
        
        users_data = [
            # Admins
            {'username': 'admin_arpit', 'role': Role.ADMIN, 'department': 'PWD', 'first_name': 'Arpit', 'last_name': 'Singh'},
            {'username': 'admin_raj', 'role': Role.ADMIN, 'department': 'PWD', 'first_name': 'Raj', 'last_name': 'Kumar'},
            {'username': 'admin_akash', 'role': Role.ADMIN, 'department': 'PWD', 'first_name': 'Akash', 'last_name': 'Sharma'},
            
            # Field Officers
            {'username': 'fo_rahul', 'role': Role.FIELD_OFFICER, 'department': 'PWD Assam', 'first_name': 'Rahul', 'last_name': 'Sharma'},
            {'username': 'fo_priya', 'role': Role.FIELD_OFFICER, 'department': 'PWD Assam', 'first_name': 'Priya', 'last_name': 'Devi'},
            {'username': 'fo_amit', 'role': Role.FIELD_OFFICER, 'department': 'PWD Meghalaya', 'first_name': 'Amit', 'last_name': 'Choudhury'},
            {'username': 'fo_sonia', 'role': Role.FIELD_OFFICER, 'department': 'PWD Assam', 'first_name': 'Sonia', 'last_name': 'Nath'},
            {'username': 'fo_rajesh', 'role': Role.FIELD_OFFICER, 'department': 'PWD Meghalaya', 'first_name': 'Rajesh', 'last_name': 'Mohan'},
            {'username': 'fo_anita', 'role': Role.FIELD_OFFICER, 'department': 'PWD Assam', 'first_name': 'Anita', 'last_name': 'Borah'},
            {'username': 'fo_vikram', 'role': Role.FIELD_OFFICER, 'department': 'PWD Meghalaya', 'first_name': 'Vikram', 'last_name': 'Sangma'},
            {'username': 'fo_megha', 'role': Role.FIELD_OFFICER, 'department': 'PWD Assam', 'first_name': 'Megha', 'last_name': 'Kalita'},
            {'username': 'fo_dipak', 'role': Role.FIELD_OFFICER, 'department': 'PWD Meghalaya', 'first_name': 'Dipak', 'last_name': 'Momin'},
            
            # Normal Users / Drivers
        ]
        
        # Generate 40 more driver usernames
        driver_names = [
            'driver_biren', 'driver_gautam', 'driver_hiren', 'driver_ismail', 'driver_jatin',
            'driver_kamal', 'driver_lalit', 'driver_mohan', 'driver_nazir', 'driver_ojhar',
            'driver_pankaj', 'driver_quaiser', 'driver_rohit', 'driver_sanjay', 'driver_tapu',
            'driver_uday', 'driver_vijay', 'driver_wahid', 'driver_xavier', 'driver_yogesh',
            'driver_zuber', 'driver_ashok', 'driver_bhaskar', 'driver_chandan', 'driver_dinesh',
            'driver_ebad', 'driver_firoz', 'driver_gopal', 'driver_hasan', 'driver_imran',
            'driver_javed', 'driver_kishore', 'driver_lakshman', 'driver_mujeeb', 'driver_nilabh',
            'driver_owais', 'driver_prabhat', 'driver_qurban', 'driver_rafiq', 'driver_satish',
        ]
        
        for name in driver_names:
            users_data.append({
                'username': name,
                'role': Role.NORMAL_USER,
                'department': 'Transport Department',
                'first_name': name.replace('driver_', '').title(),
                'last_name': 'Singh'
            })
        
        created_count = 0
        for user_data in users_data:
            role = user_data.pop('role')
            department = user_data.pop('department')
            
            user, created = User.objects.get_or_create(
                username=user_data['username'],
                defaults={
                    'email': f"{user_data['username']}@sih26002.gov.in",
                    'first_name': user_data['first_name'],
                    'last_name': user_data['last_name'],
                }
            )
            if created:
                user.set_password('Password123!')
                created_count += 1

            if role == Role.ADMIN:
                user.is_staff = True
            user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = role
            if not profile.phone:
                profile.phone = f"+9198765{random.randint(10000, 99999)}"
            profile.department = department
            profile.save()
        
        self.stdout.write(self.style.SUCCESS(f'  Created/Synced {len(users_data)} users (new: {created_count})\n'))

    def seed_districts(self):
        """Create 50+ districts with real NER geometry"""
        self.stdout.write(self.style.NOTICE('Seeding Districts...'))
        
        ner_districts = [
            # Assam districts
            {'name': 'Kamrup Metropolitan', 'state': 'Assam', 'lat': 26.15, 'lng': 91.75, 'score': 9.2},
            {'name': 'Kamrup Rural', 'state': 'Assam', 'lat': 26.25, 'lng': 91.65, 'score': 8.5},
            {'name': 'Barpeta', 'state': 'Assam', 'lat': 26.33, 'lng': 91.00, 'score': 7.8},
            {'name': 'Nagaon', 'state': 'Assam', 'lat': 26.35, 'lng': 92.68, 'score': 7.5},
            {'name': 'Dibrugarh', 'state': 'Assam', 'lat': 27.48, 'lng': 94.91, 'score': 8.2},
            {'name': 'Jorhat', 'state': 'Assam', 'lat': 26.75, 'lng': 94.20, 'score': 8.0},
            {'name': 'Tinsukia', 'state': 'Assam', 'lat': 27.49, 'lng': 95.64, 'score': 7.9},
            {'name': 'Sivasagar', 'state': 'Assam', 'lat': 26.93, 'lng': 94.64, 'score': 7.7},
            {'name': 'Golaghat', 'state': 'Assam', 'lat': 26.53, 'lng': 93.97, 'score': 7.6},
            {'name': 'Lakhimpur', 'state': 'Assam', 'lat': 27.23, 'lng': 94.11, 'score': 7.2},
            {'name': 'Dhemaji', 'state': 'Assam', 'lat': 27.48, 'lng': 94.53, 'score': 7.0},
            {'name': 'Sonitpur', 'state': 'Assam', 'lat': 26.62, 'lng': 92.75, 'score': 7.8},
            {'name': 'Darrang', 'state': 'Assam', 'lat': 26.48, 'lng': 92.17, 'score': 7.5},
            {'name': 'Udalguri', 'state': 'Assam', 'lat': 26.75, 'lng': 91.90, 'score': 7.1},
            {'name': 'Baksa', 'state': 'Assam', 'lat': 26.67, 'lng': 91.55, 'score': 7.3},
            {'name': 'Chirang', 'state': 'Assam', 'lat': 26.52, 'lng': 90.80, 'score': 6.9},
            {'name': 'Kokrajhar', 'state': 'Assam', 'lat': 26.40, 'lng': 90.27, 'score': 7.0},
            {'name': 'Dhubri', 'state': 'Assam', 'lat': 26.02, 'lng': 89.92, 'score': 7.2},
            {'name': 'South Salmara', 'state': 'Assam', 'lat': 25.85, 'lng': 89.85, 'score': 6.8},
            {'name': 'Goalpara', 'state': 'Assam', 'lat': 26.17, 'lng': 90.62, 'score': 7.4},
            
            # Meghalaya districts
            {'name': 'East Khasi Hills', 'state': 'Meghalaya', 'lat': 25.52, 'lng': 91.85, 'score': 8.5},
            {'name': 'West Khasi Hills', 'state': 'Meghalaya', 'lat': 25.50, 'lng': 91.45, 'score': 7.8},
            {'name': 'Ri-Bhoi', 'state': 'Meghalaya', 'lat': 25.85, 'lng': 91.90, 'score': 7.8},
            {'name': 'North Garo Hills', 'state': 'Meghalaya', 'lat': 25.90, 'lng': 90.50, 'score': 7.2},
            {'name': 'East Garo Hills', 'state': 'Meghalaya', 'lat': 25.65, 'lng': 90.75, 'score': 7.0},
            {'name': 'South Garo Hills', 'state': 'Meghalaya', 'lat': 25.40, 'lng': 90.55, 'score': 6.9},
            {'name': 'West Jaintia Hills', 'state': 'Meghalaya', 'lat': 25.60, 'lng': 92.30, 'score': 7.5},
            {'name': 'East Jaintia Hills', 'state': 'Meghalaya', 'lat': 25.75, 'lng': 92.45, 'score': 7.3},
            
            # Arunachal Pradesh
            {'name': 'Papum Pare', 'state': 'Arunachal Pradesh', 'lat': 27.10, 'lng': 93.70, 'score': 8.0},
            {'name': ' Lohit', 'state': 'Arunachal Pradesh', 'lat': 27.95, 'lng': 95.72, 'score': 7.5},
            {'name': 'Changlang', 'state': 'Arunachal Pradesh', 'lat': 27.70, 'lng': 96.55, 'score': 7.2},
            {'name': 'Tirap', 'state': 'Arunachal Pradesh', 'lat': 27.82, 'lng': 95.88, 'score': 7.0},
            
            # Nagaland
            {'name': 'Dimapur', 'state': 'Nagaland', 'lat': 25.87, 'lng': 93.73, 'score': 8.0},
            {'name': 'Kohima', 'state': 'Nagaland', 'lat': 25.67, 'lng': 94.10, 'score': 7.8},
            {'name': 'Mokokchung', 'state': 'Nagaland', 'lat': 26.33, 'lng': 94.52, 'score': 7.5},
            {'name': 'Tuensang', 'state': 'Nagaland', 'lat': 26.28, 'lng': 94.95, 'score': 7.0},
            
            # Manipur
            {'name': 'Imphal West', 'state': 'Manipur', 'lat': 24.82, 'lng': 93.95, 'score': 8.2},
            {'name': 'Imphal East', 'state': 'Manipur', 'lat': 24.78, 'lng': 94.08, 'score': 7.9},
            {'name': 'Thoubal', 'state': 'Manipur', 'lat': 24.65, 'lng': 94.03, 'score': 7.5},
            {'name': 'Bishnupur', 'state': 'Manipur', 'lat': 24.62, 'lng': 93.77, 'score': 7.3},
            
            # Tripura
            {'name': 'West Tripura', 'state': 'Tripura', 'lat': 23.83, 'lng': 91.28, 'score': 8.0},
            {'name': 'South Tripura', 'state': 'Tripura', 'lat': 23.50, 'lng': 91.47, 'score': 7.6},
            {'name': 'Dhalai', 'state': 'Tripura', 'lat': 23.97, 'lng': 91.80, 'score': 7.2},
            {'name': 'Sepahijala', 'state': 'Tripura', 'lat': 23.73, 'lng': 91.57, 'score': 7.0},
            
            # Mizoram
            {'name': 'Aizawl', 'state': 'Mizoram', 'lat': 23.73, 'lng': 92.72, 'score': 7.8},
            {'name': 'Lunglei', 'state': 'Mizoram', 'lat': 22.93, 'lng': 92.78, 'score': 7.5},
            {'name': 'Champhai', 'state': 'Mizoram', 'lat': 24.32, 'lng': 93.32, 'score': 7.2},
            {'name': 'Kolasib', 'state': 'Mizoram', 'lat': 24.23, 'lng': 92.68, 'score': 7.0},
            
            # Sikkim
            {'name': 'Gangtok', 'state': 'Sikkim', 'lat': 27.33, 'lng': 88.62, 'score': 8.5},
            {'name': 'Namchi', 'state': 'Sikkim', 'lat': 27.17, 'lng': 88.37, 'score': 8.0},
            {'name': 'Gyalshing', 'state': 'Sikkim', 'lat': 27.25, 'lng': 88.18, 'score': 7.5},
            {'name': 'Soreng', 'state': 'Sikkim', 'lat': 27.20, 'lng': 88.05, 'score': 7.2},
        ]
        
        count = 0
        for d in ner_districts:
            lat, lng = d['lat'], d['lng']
            # Create a 0.5 degree buffer polygon around center point
            polygon = Polygon((
                (lng - 0.5, lat - 0.5),
                (lng + 0.5, lat - 0.5),
                (lng + 0.5, lat + 0.5),
                (lng - 0.5, lat + 0.5),
                (lng - 0.5, lat - 0.5),
            ))
            
            district, created = District.objects.get_or_create(
                name=d['name'],
                defaults={
                    'state': d['state'],
                    'accessibility_score': d['score'],
                    'geom': MultiPolygon(polygon),
                    'connectivity_status': ConnectivityStatus.NORMAL,
                }
            )
            if created:
                count += 1
        
        self.stdout.write(self.style.SUCCESS(f'  Created {count} districts\n'))

    def seed_infrastructure(self):
        """Create 50+ infrastructure segments with real NER road network"""
        self.stdout.write(self.style.NOTICE('Seeding Infrastructure...'))
        
        districts = list(District.objects.all())
        if not districts:
            self.stdout.write(self.style.ERROR('  No districts found. Run seed_districts first.\n'))
            return
        
        # Create infrastructure in bulk for speed
        infra_list = []
        node_id = 2000
        
        for i, district in enumerate(districts):
            for j in range(2):  # 2 roads per district (faster)
                lat_center = 26.0 + random.uniform(-2, 2)
                lng_center = 91.8 + random.uniform(-2, 2)
                
                lat_start = lat_center + random.uniform(-0.2, 0.2)
                lng_start = lng_center + random.uniform(-0.2, 0.2)
                lat_end = lat_start + random.uniform(-0.1, 0.1)
                lng_end = lng_start + random.uniform(-0.1, 0.1)
                
                road_class = random.choice([RoadClassification.NATIONAL_HIGHWAY, RoadClassification.STATE_HIGHWAY, RoadClassification.MAJOR_DISTRICT_ROAD, RoadClassification.RURAL_ROAD])
                speed_map = {RoadClassification.NATIONAL_HIGHWAY: 50, RoadClassification.STATE_HIGHWAY: 40, RoadClassification.MAJOR_DISTRICT_ROAD: 30, RoadClassification.RURAL_ROAD: 20}
                
                infra = Infrastructure(
                    name=f"{district.name} Road {i+1}-{j+1}",
                    district=district,
                    infra_type=random.choice([InfrastructureType.ROAD, InfrastructureType.BRIDGE]),
                    road_classification=road_class,
                    start_node=node_id,
                    end_node=node_id + 1,
                    oneway=False,
                    length_km=random.uniform(5.0, 35.0),
                    base_speed_kmh=speed_map[road_class],
                    landslide_susceptibility=random.choice([HazardLevel.LOW, HazardLevel.MEDIUM, HazardLevel.HIGH]),
                    flood_hazard_zone=random.choice([HazardLevel.LOW, HazardLevel.MEDIUM, HazardLevel.HIGH]),
                    historical_landslide_count=random.randint(0, 10),
                    geom=LineString([(lng_start, lat_start), (lng_end, lat_end)]),
                    risk_score=random.uniform(0, 100),
                    risk_level=random.choice([RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]),
                )
                infra_list.append(infra)
                node_id += 2
        
        # Bulk create for speed
        Infrastructure.objects.bulk_create(infra_list)
        
        total = Infrastructure.objects.count()
        self.stdout.write(self.style.SUCCESS(f'  Created {total} infrastructure segments\n'))

    def seed_weather(self):
        """Create 50+ weather snapshots"""
        self.stdout.write(self.style.NOTICE('Seeding Weather Snapshots...'))
        
        districts = list(District.objects.all())
        
        count = 0
        now = timezone.now()
        for district in districts:
            # Create multiple weather snapshots for different times
            for days_ago in range(5):  # 5 snapshots per district
                recorded_at = now - timedelta(days=days_ago)
                
                WeatherSnapshot.objects.create(
                    district=district,
                    rainfall_mm=random.uniform(0, 120),
                    condition=random.choice([WeatherCondition.CLEAR, WeatherCondition.MODERATE, WeatherCondition.HEAVY]),
                    temperature_c=random.uniform(18, 35),
                    humidity_pct=random.uniform(50, 95),
                    wind_speed_kmh=random.uniform(5, 40),
                    weather_warning=random.choice([True, False]) if random.random() > 0.7 else False,
                    recorded_at=recorded_at,
                )
                count += 1
        
        self.stdout.write(self.style.SUCCESS(f'  Created {count} weather snapshots\n'))

    def seed_vehicles(self):
        """Create 50+ vehicles"""
        self.stdout.write(self.style.NOTICE('Seeding Vehicles...'))
        
        drivers = list(User.objects.filter(profile__role=Role.NORMAL_USER)[:40])
        
        vehicle_types = [VehicleType.TRUCK, VehicleType.VAN, VehicleType.CAR, VehicleType.EMERGENCY]
        registration_prefixes = ['AS', 'ML', 'AR', 'NL', 'TR', 'MZ', 'SK', 'MN']
        
        count = 0
        for i, driver in enumerate(drivers):
            prefix = registration_prefixes[i % len(registration_prefixes)]
            for j in range(2):  # 2 vehicles per driver
                vehicle = Vehicle.objects.create(
                    registration_number=f"{prefix}-{i+1:02d}-{random.choice(['AB', 'CD', 'EF', 'GH'])}-{1000 + i*2 + j}",
                    vehicle_type=random.choice(vehicle_types),
                    driver=driver,
                    capacity_tons=random.uniform(1.0, 20.0),
                    is_active=True,
                )
                count += 1
        
        # Create some vehicles without drivers
        for i in range(10):
            vehicle = Vehicle.objects.create(
                registration_number=f"NER-{9000 + i}",
                vehicle_type=random.choice(vehicle_types),
                capacity_tons=random.uniform(5.0, 15.0),
                is_active=True,
            )
            count += 1
        
        self.stdout.write(self.style.SUCCESS(f'  Created {count} vehicles\n'))

    def seed_location_pings(self):
        """Create 50+ location pings"""
        self.stdout.write(self.style.NOTICE('Seeding Location Pings...'))
        
        vehicles = list(Vehicle.objects.all())
        now = timezone.now()
        
        count = 0
        for vehicle in vehicles:
            # Create multiple pings per vehicle along a route
            base_lat = 26.18
            base_lng = 91.75
            
            for i in range(3):  # 3 pings per vehicle
                timestamp = now - timedelta(hours=i*2)
                
                LocationPing.objects.create(
                    vehicle=vehicle,
                    location=Point(base_lng - (i * 0.05), base_lat - (i * 0.03), srid=4326),
                    speed=random.uniform(20, 60),
                    timestamp=timestamp,
                )
                count += 1
        
        self.stdout.write(self.style.SUCCESS(f'  Created {count} location pings\n'))

    def seed_trips(self):
        """Create 50+ trips"""
        self.stdout.write(self.style.NOTICE('Seeding Trips...'))
        
        vehicles = list(Vehicle.objects.all()[:30])
        drivers = list(User.objects.filter(profile__role__in=[Role.NORMAL_USER, Role.FIELD_OFFICER]))
        
        status_choices = [TripStatus.CREATED, TripStatus.ON_ROUTE, TripStatus.DELAYED, TripStatus.DELIVERED]
        
        count = 0
        for i, vehicle in enumerate(vehicles):
            # Origin in Guwahati area
            origin_lat = 26.18 - (i * 0.01)
            origin_lng = 91.75 + (i * 0.01)
            
            # Destination in Shillong area
            dest_lat = 25.58 + (i * 0.01)
            dest_lng = 91.89 + (i * 0.01)
            
            base_eta = random.uniform(60, 180)
            predicted_eta = base_eta * random.uniform(1.0, 1.5)
            
            status = random.choice(status_choices)
            
            trip = Trip.objects.create(
                trip_code=f"TRIP-NER-{1000 + i}",
                vehicle=vehicle,
                driver=random.choice(drivers) if drivers else None,
                origin=Point(origin_lng, origin_lat, srid=4326),
                origin_name=f"Origin Point {i+1}",
                destination=Point(dest_lng, dest_lat, srid=4326),
                destination_name=f"Destination Point {i+1}",
                status=status,
                base_eta_minutes=base_eta,
                predicted_eta_minutes=predicted_eta,
                expected_delay_minutes=max(0, predicted_eta - base_eta),
                eta_factors=['Route via NH-06', 'Weather conditions normal'],
            )
            
            if status == TripStatus.ON_ROUTE:
                trip.start_time = timezone.now() - timedelta(hours=random.uniform(0.5, 3))
                trip.save()
            elif status == TripStatus.DELIVERED:
                trip.start_time = timezone.now() - timedelta(hours=5)
                trip.end_time = timezone.now() - timedelta(hours=2)
                trip.save()
            
            count += 1
        
        self.stdout.write(self.style.SUCCESS(f'  Created {count} trips\n'))

    def seed_incident_reports(self):
        """Create 50+ incident reports"""
        self.stdout.write(self.style.NOTICE('Seeding Incident Reports...'))
        
        field_officers = list(User.objects.filter(profile__role=Role.FIELD_OFFICER))
        infrastructure = list(Infrastructure.objects.all()[:30])
        
        incident_types = [IncidentType.FLOOD, IncidentType.LANDSLIDE, IncidentType.ROAD_DAMAGE, IncidentType.OBSTRUCTION]
        severity_levels = [SeverityLevel.LOW, SeverityLevel.MEDIUM, SeverityLevel.HIGH, SeverityLevel.CRITICAL]
        
        count = 0
        now = timezone.now()
        
        for i in range(50):
            lat = 26.18 - (i * 0.005)
            lng = 91.75 + (i * 0.005)
            
            officer = random.choice(field_officers) if field_officers else None
            snapped_infra = random.choice(infrastructure) if infrastructure and random.random() > 0.3 else None
            
            report = IncidentReport.objects.create(
                officer=officer,
                photo_url=f"https://ik.imagekit.io/sih26002/reports/incident_{i+1}.jpg",
                location=Point(lng, lat, srid=4326),
                snapped_infrastructure=snapped_infra,
                description=f"Road incident reported at location {i+1}",
                incident_type=random.choice(incident_types),
                severity=random.choice(severity_levels),
                client_timestamp=now - timedelta(days=random.randint(0, 30)),
                ai_issue_type=random.choice(incident_types).value if random.random() > 0.2 else '',
                ai_severity=random.choice(severity_levels).value if random.random() > 0.2 else '',
                ai_confidence=random.uniform(0.7, 0.99) if random.random() > 0.2 else None,
                analysis_status=random.choice([AnalysisStatus.COMPLETED, AnalysisStatus.PENDING]),
                status=random.choice([ReportStatus.SUBMITTED, ReportStatus.UNDER_REVIEW, ReportStatus.RESOLVED]),
            )
            count += 1
        
        self.stdout.write(self.style.SUCCESS(f'  Created {count} incident reports\n'))