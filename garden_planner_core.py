"""
Garden Planner Core Module
Contains all classes and functions for the garden planning system
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import warnings

import pandas as pd
import numpy as np
import requests
from geopy.geocoders import Nominatim

# Handle both old and new meteostat versions
try:
    from meteostat import Point, Daily
except ImportError:
    # Newer versions of meteostat changed the import structure
    try:
        from meteostat import Point
        from meteostat.daily import Daily
    except ImportError:
        # If meteostat is completely unavailable, set to None and handle gracefully
        Point = None
        Daily = None

import matplotlib.pyplot as plt
import io
import re

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.decomposition import PCA

warnings.filterwarnings('ignore')


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Application configuration"""
    DB_PATH = "garden_planner.db"
    DATA_DIR = Path("data")
    RAW_DATA_DIR = DATA_DIR / "raw"
    PROCESSED_DATA_DIR = DATA_DIR / "processed"
    
    API_TIMEOUT = 10
    
    CLIMATE_SCENARIOS = {
        'current': {'year': 2025, 'temp_offset': 0, 'precip_factor': 1.0, 'frost_factor': 1.0},
        'rcp45_2050': {'year': 2050, 'temp_offset': 1.5, 'precip_factor': 0.95, 'frost_factor': 0.7},
        'rcp85_2100': {'year': 2100, 'temp_offset': 3.5, 'precip_factor': 0.85, 'frost_factor': 0.4},
    }
    
    WEIGHTS = {
        'hardiness': 0.4,
        'shade': 0.25,
        'moisture': 0.25,
        'soil': 0.25,
        'physical': 0.15,
        'usefulness': 0.10,
    }
    
    MAX_CLUSTER_SIZE = 5


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class Location:
    """Location data model"""
    name: str
    lat: float
    lon: float
    altitude: int = 0
    microclimate: str = "plain"
    soil_type: str = "neutral_loam"
    soil_ph: float = 6.5
    geology: str = "unknown"
    subsurface_water: float = 2.0
    country: str = "Unknown"
    region: str = "Unknown"
    city: str = "Unknown"


@dataclass
class ClimateData:
    """Climate data model"""
    location_id: int
    year: int
    scenario: str
    avg_temp: float
    min_temp: float
    max_temp: float
    precip: float
    frost_days: int


# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directories"""
        Config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        Config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        Path(self.db_path).touch(exist_ok=True)
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def create_schema(self, plant_csv_path: str):
        """Create database schema dynamically from CSV"""
        df = pd.read_csv(plant_csv_path)
        columns = df.columns.tolist()
        columns_def = ', '.join([f'"{col}" TEXT' for col in columns])
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS plants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {columns_def}
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    altitude INTEGER,
                    microclimate TEXT,
                    soil_type TEXT,
                    soil_ph REAL,
                    geology TEXT,
                    subsurface_water REAL,
                    country TEXT,
                    region TEXT,
                    city TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS climate_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_id INTEGER,
                    year INTEGER,
                    avg_temp REAL,
                    min_temp REAL,
                    max_temp REAL,
                    precip REAL,
                    frost_days INTEGER,
                    scenario TEXT,
                    FOREIGN KEY (location_id) REFERENCES locations (id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location_id INTEGER,
                    plant_id INTEGER,
                    suitability_score REAL,
                    reasons TEXT,
                    companions_suggested TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (location_id) REFERENCES locations (id),
                    FOREIGN KEY (plant_id) REFERENCES plants (id)
                )
            ''')
            
            conn.commit()
    
    def load_plants(self, csv_path: str) -> int:
        """Load plants from CSV"""
        df = pd.read_csv(csv_path)
        with self.get_connection() as conn:
            df.to_sql('plants', conn, if_exists='replace', index=False)
        return len(df)
    
    def save_location(self, location: Location) -> int:
        """Save location and return its ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO locations 
                (name, lat, lon, altitude, microclimate, soil_type, soil_ph, 
                 geology, subsurface_water, country, region, city)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                location.name, location.lat, location.lon, location.altitude,
                location.microclimate, location.soil_type, location.soil_ph,
                location.geology, location.subsurface_water, location.country,
                location.region, location.city
            ))
            conn.commit()
            return cursor.lastrowid
    
    def save_climate_data(self, climate_records: List[ClimateData]):
        """Save climate data records"""
        records = [
            (c.location_id, c.year, c.avg_temp, c.min_temp, c.max_temp, 
             c.precip, c.frost_days, c.scenario)
            for c in climate_records
        ]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany('''
                INSERT INTO climate_data 
                (location_id, year, avg_temp, min_temp, max_temp, precip, frost_days, scenario)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', records)
            conn.commit()


# ============================================================================
# LOCATION DATA FETCHER
# ============================================================================

class LocationDataFetcher:
    """Fetches real geographic and environmental data from APIs"""
    
    @staticmethod
    def fetch_altitude(lat: float, lon: float) -> int:
        """Fetch altitude from Open-Elevation API"""
        try:
            url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
            response = requests.get(url, timeout=Config.API_TIMEOUT)
            if response.status_code == 200:
                return round(response.json()['results'][0]['elevation'])
        except Exception as e:
            print(f"⚠️ Altitude fetch failed: {e}")
        return 0
    
    @staticmethod
    def fetch_address(lat: float, lon: float) -> Dict[str, str]:
        """Fetch address information via reverse geocoding"""
        try:
            geolocator = Nominatim(user_agent="garden_planner_v2")
            location = geolocator.reverse((lat, lon), timeout=Config.API_TIMEOUT)
            if location:
                return location.raw.get('address', {})
        except Exception as e:
            print(f"⚠️ Geocoding failed: {e}")
        return {}
    
    @staticmethod
    def fetch_soil_ph(lat: float, lon: float) -> float:
        """Fetch soil pH from OpenLandMap"""
        try:
            url = f"https://api.openlandmap.org/soil?lat={lat}&lon={lon}&parameter_id=gnap&value=mean"
            response = requests.get(url, timeout=Config.API_TIMEOUT)
            if response.status_code == 200:
                return round(response.json()['data'][0][0], 1)
        except Exception as e:
            print(f"⚠️ Soil pH fetch failed: {e}")
        return 6.5
    
    @staticmethod
    def fetch_geology(lat: float, lon: float) -> str:
        """Fetch geology information from Macrostrat"""
        try:
            url = f"https://macrostrat.org/api/v2/point/lith?lat={lat}&lng={lon}"
            response = requests.get(url, timeout=Config.API_TIMEOUT)
            data = response.json()
            if response.status_code == 200 and data.get('success'):
                return data['data'][0]['lith'][:50]
        except Exception as e:
            print(f"⚠️ Geology fetch failed: {e}")
        return "unknown"
    
    @staticmethod
    def infer_microclimate(altitude: int) -> str:
        """Infer microclimate from altitude"""
        if altitude > 1000:
            return "mountain"
        elif altitude > 300:
            return "hilly"
        elif altitude > 100:
            return "foothills"
        return "plain"
    
    @staticmethod
    def infer_soil_type(ph: float) -> str:
        """Infer soil type from pH"""
        if ph < 6.0:
            return "acidic"
        elif ph > 7.5:
            return "alkaline"
        return "neutral_loam"
    
    def fetch_location_data(self, lat: float, lon: float, name: str = "My Garden") -> Location:
        """Fetch all location data and return Location object"""
        print(f"🌍 Fetching data for {name} ({lat:.4f}, {lon:.4f})...")
        
        altitude = self.fetch_altitude(lat, lon)
        address = self.fetch_address(lat, lon)
        soil_ph = self.fetch_soil_ph(lat, lon)
        geology = self.fetch_geology(lat, lon)
        
        location = Location(
            name=name,
            lat=lat,
            lon=lon,
            altitude=altitude,
            microclimate=self.infer_microclimate(altitude),
            soil_type=self.infer_soil_type(soil_ph),
            soil_ph=soil_ph,
            geology=geology,
            subsurface_water=2.0,
            country=address.get('country', 'Unknown'),
            region=address.get('region', 'Unknown'),
            city=address.get('city', address.get('town', 'Unknown'))
        )
        
        print("✅ Location data fetched:")
        for key, value in location.__dict__.items():
            print(f"   {key}: {value}")
        
        return location


# ============================================================================
# CLIMATE DATA FETCHER
# ============================================================================

class ClimateDataFetcher:
    """Fetches and processes climate data"""
    
    def fetch_historical_climate(self, lat: float, lon: float, 
                                start_year: int = 2015, 
                                end_year: int = 2024) -> pd.DataFrame:
        """Fetch historical climate data from Meteostat"""
        print(f"🌡️ Fetching climate data for ({lat:.4f}, {lon:.4f})...")
        
        # Check if meteostat is available
        if Point is None or Daily is None:
            print("⚠️ Meteostat library not available, using defaults")
            return pd.DataFrame()
        
        try:
            location = Point(lat, lon)
            start = datetime(start_year, 1, 1)
            end = datetime(end_year, 12, 31)
            
            data = Daily(location, start, end)
            return data.fetch()
        except Exception as e:
            print(f"⚠️ Error fetching climate data: {e}")
            print("   Using default climate values")
            return pd.DataFrame()
    
    def generate_climate_scenarios(self, location_id: int, lat: float, lon: float) -> List[ClimateData]:
        """Generate climate scenarios (historical + projections)"""
        df = self.fetch_historical_climate(lat, lon)
        
        if df.empty:
            print("⚠️ No climate data available, using defaults")
            return self._default_climate_data(location_id)
        
        avg_temp = df['tavg'].mean()
        min_temp = df['tmin'].min()
        max_temp = df['tmax'].max()
        precip = df['prcp'].sum() / len(df.index.year.unique())
        frost_days = (df['tmin'] <= 0).sum() / len(df.index.year.unique())
        
        climate_records = []
        
        for scenario_name, params in Config.CLIMATE_SCENARIOS.items():
            climate_records.append(ClimateData(
                location_id=location_id,
                year=params['year'],
                scenario=scenario_name,
                avg_temp=round(avg_temp + params['temp_offset'], 1),
                min_temp=round(min_temp + params['temp_offset'] * 0.7, 1),
                max_temp=round(max_temp + params['temp_offset'] * 1.3, 1),
                precip=round(precip * params['precip_factor'], 0),
                frost_days=int(frost_days * params['frost_factor'])
            ))
        
        print(f"✅ Generated {len(climate_records)} climate scenarios")
        return climate_records
    
    def _default_climate_data(self, location_id: int) -> List[ClimateData]:
        """Default climate data"""
        return [
            ClimateData(location_id, 2025, 'current', 12.0, -15.0, 35.0, 600.0, 60),
            ClimateData(location_id, 2050, 'rcp45_2050', 13.5, -13.0, 37.0, 570.0, 42),
            ClimateData(location_id, 2100, 'rcp85_2100', 15.5, -11.0, 39.5, 510.0, 24),
        ]


# ============================================================================
# PLANT SUITABILITY CALCULATOR (continued in next message due to length)
# ============================================================================

class VectorizedPlantSuitabilityCalculator:
    """Calculates suitability scores using vectorized operations"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
    
    def calculate_suitability(self, location_id: int, top_n: int = 100, min_score: float = 0.3) -> pd.DataFrame:
        """Calculate suitability scores"""
        print(f"🌱 Calculating plant suitability for location {location_id}...")
        
        with self.db.get_connection() as conn:
            location = pd.read_sql(f"SELECT * FROM locations WHERE id = {location_id}", conn).iloc[0]
            climate = pd.read_sql(f"SELECT * FROM climate_data WHERE location_id = {location_id} AND scenario = 'current' LIMIT 1", conn)
            
            if climate.empty:
                climate_data = {'avg_temp': 12.0, 'frost_days': 60, 'precip': 600}
            else:
                climate_data = climate.iloc[0].to_dict()
            
            plants = pd.read_sql("SELECT * FROM plants", conn)
        
        scores_df = self._vectorized_score_all_plants(plants, location, climate_data)
        scores_df = scores_df[scores_df['suitability_score'] >= min_score]
        scores_df = scores_df.sort_values('suitability_score', ascending=False).head(top_n)
        
        if not scores_df.empty:
            self._save_recommendations(location_id, scores_df)
        
        print(f"✅ Found {len(scores_df)} suitable plants")
        return scores_df
    
    def _vectorized_score_all_plants(self, plants: pd.DataFrame, location: pd.Series, climate: Dict) -> pd.DataFrame:
        """Vectorized scoring"""
        n_plants = len(plants)
        total_scores = np.zeros(n_plants)
        
        avg_temp = climate['avg_temp']
        precip = climate['precip']
        soil_ph = location['soil_ph']
        soil_type = location['soil_type']
        microclimate = location['microclimate']
        
        hardiness_scores = self._vectorized_hardiness(plants.get('hardiness', pd.Series([''] * n_plants)).fillna('').astype(str), avg_temp)
        total_scores += hardiness_scores * Config.WEIGHTS['hardiness']
        
        shade_scores = self._vectorized_shade(plants.get('shade', pd.Series([''] * n_plants)).fillna('').astype(str), avg_temp, precip)
        total_scores += shade_scores * Config.WEIGHTS['shade']
        
        moisture_scores = self._vectorized_moisture(plants.get('moisture', pd.Series([''] * n_plants)).fillna('').astype(str), precip)
        total_scores += moisture_scores * Config.WEIGHTS['moisture']
        
        soil_scores = self._vectorized_soil(plants.get('soil', pd.Series([''] * n_plants)).fillna('').astype(str), soil_type, soil_ph)
        total_scores += soil_scores * Config.WEIGHTS['soil']
        
        physical_scores = self._vectorized_physical(
            plants.get('habit', pd.Series([''] * n_plants)).fillna('').astype(str),
            plants.get('growth', pd.Series([''] * n_plants)).fillna('').astype(str),
            microclimate
        )
        total_scores += physical_scores * Config.WEIGHTS['physical']
        
        usefulness_scores = self._vectorized_usefulness(
            plants.get('edibility_rating', pd.Series([0] * n_plants)).fillna(0),
            plants.get('medicinal_rating', pd.Series([0] * n_plants)).fillna(0),
            plants.get('other_uses_rating', pd.Series([0] * n_plants)).fillna(0)
        )
        total_scores += usefulness_scores * Config.WEIGHTS['usefulness']
        
        hazards = plants.get('known_hazards', pd.Series([''] * n_plants)).fillna('').astype(str).str.lower()
        hazard_mask = hazards.str.contains('poison|toxic', na=False)
        total_scores = np.where(hazard_mask, total_scores * 0.7, total_scores)
        
        results = pd.DataFrame({
            'plant_id': range(1, n_plants + 1),
            'latin_name': plants.get('latin_name', 'Unknown'),
            'common_name': plants.get('common_name', 'Unknown'),
            'suitability_score': np.round(total_scores, 3),
            'hardiness': plants.get('hardiness', ''),
            'habit': plants.get('habit', ''),
            'edibility': plants.get('edibility_rating', 0),
            'moisture': plants.get('moisture', 0),
            'soil': plants.get('soil', 0),
            'shade': plants.get('shade', 0),
            'medicinal': plants.get('medicinal_rating', 0),
            'reasons': ["Suitable conditions"] * n_plants
        })
        
        return results
    
    def _vectorized_hardiness(self, hardiness_series: pd.Series, avg_temp: float) -> np.ndarray:
        n = len(hardiness_series)
        scores = np.full(n, 0.5)
        location_zone = 6 + (avg_temp - 10) / 10
        hardiness_clean = hardiness_series.str.replace('H', '', regex=False).str.strip()
        
        for idx, zone_str in enumerate(hardiness_clean):
            if not zone_str:
                continue
            try:
                parts = zone_str.split('-')
                if len(parts) >= 2:
                    min_zone = float(parts[0])
                    max_zone = float(parts[1])
                    if min_zone <= location_zone <= max_zone:
                        scores[idx] = 1.0
                    elif location_zone >= min_zone - 1:
                        scores[idx] = 0.7
                    else:
                        scores[idx] = 0.2
            except:
                pass
        return scores
    
    def _vectorized_shade(self, shade_series: pd.Series, avg_temp: float, precip: float) -> np.ndarray:
        shade_lower = shade_series.str.lower()
        full_sun_mask = shade_lower.str.contains('full sun', na=False)
        shade_mask = shade_lower.str.contains('shade', na=False) & ~full_sun_mask
        scores = np.full(len(shade_series), 0.8)
        scores = np.where(full_sun_mask, 1.0 if avg_temp > 10 else 0.8, scores)
        scores = np.where(shade_mask, 0.9 if precip > 700 else 0.7, scores)
        return scores
    
    def _vectorized_moisture(self, moisture_series: pd.Series, precip: float) -> np.ndarray:
        moisture_lower = moisture_series.str.lower()
        moist_mask = moisture_lower.str.contains('moist|wet', na=False)
        dry_mask = moisture_lower.str.contains('dry', na=False)
        scores = np.full(len(moisture_series), 0.8)
        scores = np.where(moist_mask, 1.0 if precip > 700 else 0.6, scores)
        scores = np.where(dry_mask, 1.0 if precip < 600 else 0.7, scores)
        return scores
    
    def _vectorized_soil(self, soil_series: pd.Series, soil_type: str, soil_ph: float) -> np.ndarray:
        soil_lower = soil_series.str.lower()
        loam_mask = soil_lower.str.contains('loam', na=False)
        acid_mask = soil_lower.str.contains('acid', na=False)
        alkal_mask = soil_lower.str.contains('alkal', na=False)
        scores = np.full(len(soil_series), 0.3)
        
        if 'loam' in soil_type:
            scores = np.where(loam_mask, 0.5, scores)
        if 'acidic' in soil_type:
            scores = np.where(acid_mask, 0.5, scores)
        if 'alkaline' in soil_type:
            scores = np.where(alkal_mask, 0.5, scores)
        
        ph_bonus = np.zeros(len(soil_series))
        ph_bonus = np.where(acid_mask & (soil_ph < 6.5), 0.5, ph_bonus)
        ph_bonus = np.where(alkal_mask & (soil_ph > 7.0), 0.5, ph_bonus)
        ph_bonus = np.where((~acid_mask) & (~alkal_mask) & (soil_ph >= 6.0) & (soil_ph <= 7.5), 0.4, ph_bonus)
        scores = np.minimum(scores + ph_bonus, 1.0)
        return scores
    
    def _vectorized_physical(self, habit_series: pd.Series, growth_series: pd.Series, microclimate: str) -> np.ndarray:
        habit_lower = habit_series.str.lower()
        growth_lower = growth_series.str.lower()
        woody_mask = habit_lower.str.contains('shrub|tree', na=False)
        herb_mask = habit_lower.str.contains('perennial|annual', na=False)
        ground_mask = habit_lower.str.contains('ground cover', na=False)
        
        habit_scores = np.full(len(habit_series), 0.8)
        if microclimate in ['plain', 'foothills']:
            habit_scores = np.where(woody_mask, 0.9, habit_scores)
        else:
            habit_scores = np.where(woody_mask, 0.7, habit_scores)
        habit_scores = np.where(herb_mask, 1.0, habit_scores)
        habit_scores = np.where(ground_mask, 0.95, habit_scores)
        
        fast_mask = growth_lower.str.contains('fast', na=False)
        medium_mask = growth_lower.str.contains('medium', na=False)
        growth_scores = np.full(len(growth_series), 0.6)
        growth_scores = np.where(fast_mask, 1.0, growth_scores)
        growth_scores = np.where(medium_mask, 0.8, growth_scores)
        
        return (habit_scores + growth_scores) / 2
    
    def _vectorized_usefulness(self, edibility: pd.Series, medicinal: pd.Series, other_uses: pd.Series) -> np.ndarray:
        edib = pd.to_numeric(edibility, errors='coerce').fillna(0).values
        med = pd.to_numeric(medicinal, errors='coerce').fillna(0).values
        other = pd.to_numeric(other_uses, errors='coerce').fillna(0).values
        return (edib + med + other) / 3.0
    
    def _save_recommendations(self, location_id: int, results: pd.DataFrame):
        with self.db.get_connection() as conn:
            results_copy = results.copy()
            results_copy['location_id'] = location_id
            results_copy[['location_id', 'plant_id', 'suitability_score', 'reasons']].to_sql(
                'recommendations', conn, if_exists='append', index=False
            )


# ============================================================================
# COMPANION PLANT MATCHING HELPER
# ============================================================================

class CompanionMatcher:
    """Enhanced companion plant matching with synonym support"""
    
    # Mapping of companion plant terms to common variations
    SYNONYM_MAP = {
        # Alliums family
        'alliums': ['onion', 'garlic', 'leek', 'chive', 'shallot', 'scallion', 'allium'],
        
        # Brassicas family
        'brassicas': ['cabbage', 'broccoli', 'cauliflower', 'kale', 'brussels sprout', 
                      'kohlrabi', 'turnip', 'radish', 'mustard'],
        
        # Nightshades
        'nightshades': ['tomato', 'potato', 'pepper', 'eggplant', 'capsicum', 'aubergine'],
        
        # Beans
        'beans': ['bean', 'fava', 'broad bean', 'runner bean', 'french bean', 
                  'kidney bean', 'navy bean', 'pinto bean', 'black bean', 'lima bean'],
        'beans, bush': ['bush bean', 'bean'],
        'beans, pole': ['pole bean', 'runner bean', 'bean'],
        
        # Squash family
        'squash': ['pumpkin', 'zucchini', 'courgette', 'marrow', 'gourd', 'squash'],
        'cucurbits': ['cucumber', 'melon', 'pumpkin', 'squash', 'zucchini', 'gourd'],
        
        # Grains
        'corn': ['maize', 'sweet corn', 'corn'],
        'wheat': ['wheat', 'triticum'],
        
        # Herbs
        'mint': ['peppermint', 'spearmint', 'mentha', 'mint'],
        'basil': ['basil', 'ocimum'],
        'parsley': ['parsley', 'petroselinum'],
        
        # Fruits
        'fruit trees': ['apple', 'pear', 'cherry', 'plum', 'peach', 'apricot', 
                       'fig', 'mulberry', 'citrus', 'orange', 'lemon'],
        'berries': ['strawberry', 'raspberry', 'blackberry', 'blueberry', 
                   'currant', 'gooseberry'],
        
        # Other vegetables
        'carrots': ['carrot'],
        'tomatoes': ['tomato'],
        'potatoes': ['potato'],
        'peppers': ['pepper', 'capsicum'],
        'cabbages': ['cabbage'],
        'lettuce': ['lettuce'],
        'cucumbers': ['cucumber'],
        'peas': ['pea'],
        'spinach': ['spinach'],
    }
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """Normalize plant name for matching"""
        if not name or pd.isna(name):
            return ""
        
        name = str(name).lower().strip()
        
        # Remove common suffixes that might interfere
        name = re.sub(r'\s+(tree|plant|bush|shrub|vine)$', '', name)
        
        # Handle comma-separated names like "beans, bush"
        if ',' in name:
            # Take the main part before comma
            name = name.split(',')[0].strip()
        
        return name
    
    @staticmethod
    def get_search_terms(companion_name: str) -> set:
        """
        Get all search terms for a companion plant name
        Returns both the original name and any synonyms
        """
        normalized = CompanionMatcher.normalize_name(companion_name)
        search_terms = {normalized}
        
        # Add synonyms if available
        if normalized in CompanionMatcher.SYNONYM_MAP:
            search_terms.update(CompanionMatcher.SYNONYM_MAP[normalized])
        
        # Also check the original (non-normalized) in case it's in the map
        original_lower = str(companion_name).lower().strip()
        if original_lower in CompanionMatcher.SYNONYM_MAP:
            search_terms.update(CompanionMatcher.SYNONYM_MAP[original_lower])
        
        return search_terms
    
    @staticmethod
    def plant_name_matches(plant_name: str, search_terms: set) -> bool:
        """
        Check if a plant name matches any of the search terms
        Uses word boundary matching to avoid false positives
        """
        if not plant_name:
            return False
        
        plant_name_normalized = CompanionMatcher.normalize_name(plant_name)
        
        for term in search_terms:
            # Exact match
            if term == plant_name_normalized:
                return True
            
            # Substring match with some flexibility
            # "tomato" matches "cherry tomato", "tree tomato", etc.
            if term in plant_name_normalized or plant_name_normalized in term:
                return True
            
            # Word boundary match - term appears as a complete word
            # This prevents "pea" from matching "chickpea"
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, plant_name_normalized):
                return True
        
        return False


# ============================================================================
# CLUSTERING MODULE
# ============================================================================

class PlantClusteringModule:
    """Handles plant clustering and companion analysis"""
    
    @staticmethod
    def prepare_features(X: pd.DataFrame) -> np.ndarray:
        X = X.copy().fillna("unknown")
        for col in X.select_dtypes(include=["object"]).columns:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
        scaler = StandardScaler()
        num_cols = X.select_dtypes(include=[np.number]).columns
        if len(num_cols) > 0:
            X[num_cols] = scaler.fit_transform(X[num_cols])
        return X.values
    
    @staticmethod
    def cluster_plants(df: pd.DataFrame, max_size: int = Config.MAX_CLUSTER_SIZE) -> pd.DataFrame:
        """Cluster plants ensuring max size per cluster"""
        print(f"🔬 Clustering plants (max {max_size} per cluster)...")
        
        trait_cols = ["hardiness", "habit", "soil", "shade", "moisture", "edibility", "medicinal", "suitability_score"]
        X_raw = df[trait_cols].copy()
        X = PlantClusteringModule.prepare_features(X_raw)
        
        n_plants = len(df)
        k_coarse = max(1, n_plants // max_size)
        
        kmeans = KMeans(n_clusters=k_coarse, random_state=42, n_init=10)
        df["coarse_cluster"] = kmeans.fit_predict(X)
        
        final_cluster_labels = np.zeros(n_plants, dtype=int)
        current_label = 0
        
        for cc in sorted(df["coarse_cluster"].unique()):
            idx = np.where(df["coarse_cluster"].values == cc)[0]
            group_size = len(idx)
            
            if group_size <= max_size:
                final_cluster_labels[idx] = current_label
                current_label += 1
            else:
                sub_k = int(np.ceil(group_size / max_size))
                k_sub = KMeans(n_clusters=sub_k, random_state=42, n_init=10)
                sub_labels = k_sub.fit_predict(X[idx])
                
                for s in range(sub_k):
                    idx_sub = idx[sub_labels == s]
                    final_cluster_labels[idx_sub] = current_label
                    current_label += 1
        
        df["cluster"] = final_cluster_labels
        n_final = df["cluster"].nunique()
        print(f"✅ Created {n_final} clusters")
        
        print("\n================= CLUSTERS =================")
        for c in sorted(df["cluster"].unique()):
            group = df[df["cluster"] == c]
            names = group["common_name"].fillna(group["latin_name"])
            print(f"\nCluster {c} (size={len(group)}):")
            for name in names:
                print(f"  - {name}")
        
        return df
    
    @staticmethod
    def visualize_clusters(df: pd.DataFrame, garden_name: str):
        """Create cluster visualization"""
        trait_cols = ["hardiness", "habit", "soil", "shade", "moisture", "edibility", "medicinal", "suitability_score"]
        X_raw = df[trait_cols].copy()
        X = PlantClusteringModule.prepare_features(X_raw)
        
        pca = PCA(n_components=2)
        X_2d = pca.fit_transform(X)
        
        n_clusters = df["cluster"].nunique()
        fig, ax = plt.subplots(figsize=(10, 8))
        colors = plt.cm.tab20(np.linspace(0, 1, n_clusters))
        
        for i, c in enumerate(sorted(df["cluster"].unique())):
            mask = df["cluster"] == c
            ax.scatter(X_2d[mask, 0], X_2d[mask, 1], s=80, c=[colors[i]], alpha=0.85, edgecolors="black", label=f"C{c} (n={mask.sum()})")
        
        ax.set_xlabel("PCA 1")
        ax.set_ylabel("PCA 2")
        ax.set_title(f"Plant Clusters - {garden_name}")
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(f"plant_clusters_max{Config.MAX_CLUSTER_SIZE}.png", dpi=300, bbox_inches="tight")
        plt.show()
        
        return fig
    
    @staticmethod
    def find_companions(df: pd.DataFrame, companion_csv: str) -> Dict[int, pd.DataFrame]:
        """Find companion plant relationships within clusters using improved matching"""
        suit = pd.read_csv(companion_csv)
        cluster_companions = {}
        
        for cl in sorted(df["cluster"].unique()):
            cluster_plants = df[df["cluster"] == cl]
            cluster_names = cluster_plants["common_name"].fillna("").tolist()
            
            matching_rows = []
            
            for idx, row in suit.iterrows():
                source_node = str(row["Source Node"])
                dest_node = str(row["Destination Node"])
                
                # Get search terms for both source and destination (with synonyms)
                source_terms = CompanionMatcher.get_search_terms(source_node)
                dest_terms = CompanionMatcher.get_search_terms(dest_node)
                
                # Check if any cluster plant matches source or destination
                source_in_cluster = any(
                    CompanionMatcher.plant_name_matches(name, source_terms) 
                    for name in cluster_names
                )
                dest_in_cluster = any(
                    CompanionMatcher.plant_name_matches(name, dest_terms) 
                    for name in cluster_names
                )
                
                # Both plants must be in the same cluster
                if source_in_cluster and dest_in_cluster:
                    matching_rows.append(row)
            
            if matching_rows:
                cluster_companions[cl] = pd.DataFrame(matching_rows)[["Source Node", "Link", "Destination Node", "Source Type"]]
                print(f"Cluster {cl}: {len(matching_rows)} companion relationships")
        
        return cluster_companions
    
    @staticmethod
    def export_to_excel(df: pd.DataFrame, companions: Dict[int, pd.DataFrame], fig, garden_name: str, filename: str):
        """Export all results to Excel"""
        cluster_df = df[[
            "plant_id", "latin_name", "common_name", "suitability_score",
            "hardiness", "habit", "soil", "shade", "moisture",
            "edibility", "medicinal", "cluster"
        ]].copy()
        
        with pd.ExcelWriter(filename, engine="xlsxwriter") as writer:
            cluster_df.to_excel(writer, sheet_name="clusters", index=False)
            
            for cl, df_cl in companions.items():
                sheet_name = f"cluster_{cl}_companions"
                df_cl.to_excel(writer, sheet_name=sheet_name, index=False)
            
            workbook = writer.book
            ws_plot = workbook.add_worksheet("clusters_plot")
            ws_plot.write(0, 0, f"Garden: {garden_name}")
            
            img = io.BytesIO()
            fig.savefig(img, format="png", dpi=200, bbox_inches="tight")
            img.seek(0)
            ws_plot.insert_image("B3", "", {"image_data": img})


# ============================================================================
# MAIN APPLICATION CLASS
# ============================================================================

class GardenPlanner:
    """Main application orchestrator"""
    
    def __init__(self, db_path: str = Config.DB_PATH, use_vectorized: bool = True):
        self.db = DatabaseManager(db_path)
        self.location_fetcher = LocationDataFetcher()
        self.climate_fetcher = ClimateDataFetcher()
        self.calculator = VectorizedPlantSuitabilityCalculator(self.db)
    
    def initialize(self, plant_csv_path: str):
        """Initialize database and load plant data"""
        print("🚀 Initializing Garden Planner...")
        self.db.create_schema(plant_csv_path)
        count = self.db.load_plants(plant_csv_path)
        print(f"✅ Loaded {count} plants from {plant_csv_path}")
    
    def add_location(self, lat: float, lon: float, name: str = "My Garden") -> int:
        """Add a new garden location"""
        location = self.location_fetcher.fetch_location_data(lat, lon, name)
        location_id = self.db.save_location(location)
        climate_data = self.climate_fetcher.generate_climate_scenarios(location_id, lat, lon)
        self.db.save_climate_data(climate_data)
        print(f"✅ Location '{name}' added with ID: {location_id}")
        return location_id
    
    def get_recommendations(self, location_id: int, top_n: int = 100, min_score: float = 0.5) -> pd.DataFrame:
        """Get plant recommendations"""
        results = self.calculator.calculate_suitability(location_id, top_n, min_score)
        
        if not results.empty:
            print("\n🎯 TOP RECOMMENDATIONS:")
            print(results[['latin_name', 'common_name', 'suitability_score']].head(10).to_string(index=False))
        
        return results
    
    def export_recommendations(self, location_id: int, filepath: str):
        """Export recommendations to CSV"""
        results = self.get_recommendations(location_id)
        results.to_csv(filepath, index=False)
        print(f"📄 Exported to {filepath}")
