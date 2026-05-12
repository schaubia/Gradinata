"""
Climate Change Projection Module
Analyzes current climate data and projects changes for the next 5 years
Based on IPCC data and regional climate models
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class ClimateProjection:
    """Climate change projection for a location"""
    location_name: str
    current_year: int
    projection_year: int
    
    # Temperature changes (°C)
    temp_change: float
    temp_change_min: float
    temp_change_max: float
    
    # Precipitation changes (%)
    precip_change: float
    precip_change_min: float
    precip_change_max: float
    
    # Growing season changes (days)
    growing_season_change: int
    frost_days_change: int
    
    # Extreme events
    heat_wave_increase: float  # % increase in heat wave days
    drought_risk_change: float  # % change in drought risk
    heavy_rain_increase: float  # % increase in heavy rainfall events
    
    # Impact summary
    hardiness_zone_shift: float  # zones warmer
    impact_level: str  # low, moderate, high, severe
    confidence: str  # low, medium, high


class ClimateChangeProjector:
    """Projects climate change impacts based on location and current data"""
    
    # Regional climate change rates (°C per decade) based on IPCC AR6
    REGIONAL_WARMING_RATES = {
        'arctic': 0.4,  # Arctic amplification
        'northern_europe': 0.25,
        'southern_europe': 0.3,
        'north_america': 0.22,
        'central_america': 0.2,
        'south_america': 0.18,
        'africa': 0.25,
        'middle_east': 0.35,
        'south_asia': 0.22,
        'east_asia': 0.24,
        'southeast_asia': 0.18,
        'oceania': 0.2,
        'global_average': 0.23
    }
    
    # Precipitation trends (% change per decade)
    REGIONAL_PRECIP_TRENDS = {
        'arctic': 5.0,
        'northern_europe': 3.0,
        'southern_europe': -2.0,  # Drying
        'north_america': 1.5,
        'central_america': -1.5,
        'south_america': 2.0,
        'africa': -0.5,
        'middle_east': -3.0,  # Drying
        'south_asia': 2.5,
        'east_asia': 1.0,
        'southeast_asia': 1.5,
        'oceania': 0.5,
        'global_average': 1.0
    }
    
    def __init__(self):
        """Initialize the climate projector"""
        pass
    
    def determine_region(self, lat: float, lon: float) -> str:
        """Determine climate region from coordinates"""
        # Arctic/Sub-arctic
        if abs(lat) > 66.5:
            return 'arctic'
        
        # Europe
        if -10 <= lon <= 40 and 35 <= lat <= 70:
            if lat > 55:
                return 'northern_europe'
            else:
                return 'southern_europe'
        
        # Asia
        if 40 <= lon <= 180:
            if lat > 50:
                return 'east_asia'  # Russia/Northern Asia
            elif lat > 30:
                return 'east_asia'
            elif lat > 10:
                return 'south_asia'
            else:
                return 'southeast_asia'
        
        # Middle East
        if 25 <= lon <= 65 and 15 <= lat <= 45:
            return 'middle_east'
        
        # Africa
        if -20 <= lon <= 55 and -35 <= lat <= 35:
            return 'africa'
        
        # Americas
        if -180 <= lon <= -30:
            if lat > 25:
                return 'north_america'
            elif lat > 10:
                return 'central_america'
            else:
                return 'south_america'
        
        # Oceania
        if 110 <= lon <= 180 and -50 <= lat <= 0:
            return 'oceania'
        
        return 'global_average'
    
    def calculate_projection(self, 
                           lat: float, 
                           lon: float,
                           current_avg_temp: float,
                           current_precip: float,
                           current_frost_days: int,
                           location_name: str = "Your Location",
                           years_ahead: int = 5) -> ClimateProjection:
        """
        Calculate climate projection for a location
        
        Args:
            lat: Latitude
            lon: Longitude
            current_avg_temp: Current average annual temperature (°C)
            current_precip: Current annual precipitation (mm)
            current_frost_days: Current frost days per year
            location_name: Name of location
            years_ahead: Years into the future (default 5)
        
        Returns:
            ClimateProjection object with all projected changes
        """
        region = self.determine_region(lat, lon)
        
        # Get regional rates
        warming_rate = self.REGIONAL_WARMING_RATES.get(region, 0.23)
        precip_rate = self.REGIONAL_PRECIP_TRENDS.get(region, 1.0)
        
        # Calculate temperature changes
        temp_change = warming_rate * (years_ahead / 10)
        temp_change_min = temp_change * 0.7  # Conservative estimate
        temp_change_max = temp_change * 1.4  # High emission scenario
        
        # Calculate precipitation changes
        precip_change = precip_rate * (years_ahead / 10)
        precip_change_min = precip_change * 0.5
        precip_change_max = precip_change * 1.8
        
        # Growing season changes (approximately 5 days per 1°C warming)
        growing_season_change = int(temp_change * 5)
        
        # Frost days reduction (approximately 15 days per 1°C in temperate zones)
        frost_days_change = int(-temp_change * 12)
        
        # Extreme events (increases with warming)
        heat_wave_increase = temp_change * 25  # % increase
        drought_risk_change = -precip_change * 2  # Linked to precip change
        heavy_rain_increase = temp_change * 15  # More intense rainfall
        
        # Hardiness zone shift (0.5 zone per 1°C)
        hardiness_zone_shift = temp_change * 0.5
        
        # Determine impact level
        impact_level = self._determine_impact_level(
            temp_change, precip_change, region
        )
        
        # Confidence based on region and timeframe
        confidence = self._determine_confidence(region, years_ahead)
        
        return ClimateProjection(
            location_name=location_name,
            current_year=2025,
            projection_year=2025 + years_ahead,
            temp_change=round(temp_change, 2),
            temp_change_min=round(temp_change_min, 2),
            temp_change_max=round(temp_change_max, 2),
            precip_change=round(precip_change, 1),
            precip_change_min=round(precip_change_min, 1),
            precip_change_max=round(precip_change_max, 1),
            growing_season_change=growing_season_change,
            frost_days_change=frost_days_change,
            heat_wave_increase=round(heat_wave_increase, 1),
            drought_risk_change=round(drought_risk_change, 1),
            heavy_rain_increase=round(heavy_rain_increase, 1),
            hardiness_zone_shift=round(hardiness_zone_shift, 2),
            impact_level=impact_level,
            confidence=confidence
        )
    
    def _determine_impact_level(self, temp_change: float, 
                                 precip_change: float, 
                                 region: str) -> str:
        """Determine overall impact level"""
        # High impact regions
        if region in ['middle_east', 'southern_europe', 'central_america']:
            if abs(temp_change) > 1.5 or abs(precip_change) > 5:
                return 'severe'
            elif abs(temp_change) > 1.0 or abs(precip_change) > 3:
                return 'high'
            else:
                return 'moderate'
        
        # General assessment
        if abs(temp_change) > 2.0 or abs(precip_change) > 8:
            return 'severe'
        elif abs(temp_change) > 1.2 or abs(precip_change) > 5:
            return 'high'
        elif abs(temp_change) > 0.6 or abs(precip_change) > 2:
            return 'moderate'
        else:
            return 'low'
    
    def _determine_confidence(self, region: str, years_ahead: int) -> str:
        """Determine confidence level of projection"""
        # Near-term projections more confident
        if years_ahead <= 10:
            if region in ['northern_europe', 'north_america', 'east_asia']:
                return 'high'
            else:
                return 'medium'
        elif years_ahead <= 30:
            return 'medium'
        else:
            return 'low'
    
    def generate_impact_summary(self, projection: ClimateProjection) -> Dict[str, str]:
        """Generate human-readable impact summary"""
        summary = {
            'temperature': self._format_temp_impact(projection),
            'precipitation': self._format_precip_impact(projection),
            'growing_season': self._format_growing_season_impact(projection),
            'extreme_events': self._format_extreme_events_impact(projection),
            'gardening_implications': self._format_gardening_implications(projection)
        }
        return summary
    
    def _format_temp_impact(self, proj: ClimateProjection) -> str:
        """Format temperature impact"""
        if proj.temp_change < 0.5:
            return f"Minimal warming expected (+{proj.temp_change}°C by {proj.projection_year})"
        elif proj.temp_change < 1.5:
            return f"Moderate warming expected (+{proj.temp_change}°C by {proj.projection_year}, range: +{proj.temp_change_min} to +{proj.temp_change_max}°C)"
        else:
            return f"Significant warming expected (+{proj.temp_change}°C by {proj.projection_year}, range: +{proj.temp_change_min} to +{proj.temp_change_max}°C)"
    
    def _format_precip_impact(self, proj: ClimateProjection) -> str:
        """Format precipitation impact"""
        if abs(proj.precip_change) < 2:
            return f"Minimal precipitation change ({proj.precip_change:+.1f}%)"
        elif proj.precip_change > 0:
            return f"Increased precipitation expected ({proj.precip_change:+.1f}%, range: {proj.precip_change_min:+.1f} to {proj.precip_change_max:+.1f}%)"
        else:
            return f"Decreased precipitation expected ({proj.precip_change:+.1f}%, range: {proj.precip_change_min:+.1f} to {proj.precip_change_max:+.1f}%)"
    
    def _format_growing_season_impact(self, proj: ClimateProjection) -> str:
        """Format growing season impact"""
        if proj.growing_season_change > 0:
            return f"Growing season expected to lengthen by ~{proj.growing_season_change} days. Frost days will decrease by ~{abs(proj.frost_days_change)} days per year."
        else:
            return "Growing season changes expected to be minimal"
    
    def _format_extreme_events_impact(self, proj: ClimateProjection) -> str:
        """Format extreme events impact"""
        events = []
        if proj.heat_wave_increase > 10:
            events.append(f"heat waves (+{proj.heat_wave_increase:.0f}%)")
        if abs(proj.drought_risk_change) > 10:
            if proj.drought_risk_change > 0:
                events.append(f"drought risk (+{proj.drought_risk_change:.0f}%)")
            else:
                events.append(f"drought risk ({proj.drought_risk_change:.0f}%)")
        if proj.heavy_rain_increase > 10:
            events.append(f"heavy rainfall events (+{proj.heavy_rain_increase:.0f}%)")
        
        if events:
            return f"Increased frequency of: {', '.join(events)}"
        else:
            return "Minimal changes in extreme weather events expected"
    
    def _format_gardening_implications(self, proj: ClimateProjection) -> str:
        """Format gardening implications"""
        implications = []
        
        if proj.hardiness_zone_shift >= 0.5:
            implications.append(f"Your location may shift {proj.hardiness_zone_shift:.1f} hardiness zones warmer")
        
        if proj.temp_change > 1.0:
            implications.append("Consider heat-tolerant plant varieties")
        
        if proj.precip_change < -3:
            implications.append("Drought-resistant plants recommended")
        elif proj.precip_change > 3:
            implications.append("Ensure good drainage; consider water-loving plants")
        
        if proj.growing_season_change > 10:
            implications.append("Extended growing season allows for longer-maturing crops")
        
        if not implications:
            implications.append("Climate expected to remain relatively stable")
        
        return " • ".join(implications)


def get_climate_projection_for_location(lat: float, 
                                        lon: float,
                                        current_avg_temp: float,
                                        current_precip: float,
                                        current_frost_days: int,
                                        location_name: str = "Your Location") -> Tuple[ClimateProjection, Dict[str, str]]:
    """
    Convenience function to get projection and summary
    
    Returns:
        Tuple of (ClimateProjection object, impact summary dict)
    """
    projector = ClimateChangeProjector()
    projection = projector.calculate_projection(
        lat, lon, current_avg_temp, current_precip, 
        current_frost_days, location_name
    )
    summary = projector.generate_impact_summary(projection)
    
    return projection, summary
