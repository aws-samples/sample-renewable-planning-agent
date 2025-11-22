import math
import numpy as np
import requests
import logging
import os
from typing import Tuple, Optional, List
from strands.tools import tool
import io
from PIL import Image
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import tempfile

from .storage_utils import load_file_from_storage, save_file_with_storage

# Constants
EARTH_RADIUS_M = 6371000
METERS_PER_LAT_DEGREE = 111320

# Configure logging
logger = logging.getLogger(__name__)

# Global counter for image IDs
_image_counter = {}

def get_next_image_id(project_id: str, image_type: str = "layout") -> int:
    """Get the next incremental image ID for a project and image type."""
    key = f"{project_id}_{image_type}"
    if key not in _image_counter:
        _image_counter[key] = 0
    _image_counter[key] += 1
    return _image_counter[key]

def get_prevailing_wind_direction(wind_conditions: dict) -> float:
    """Calculate prevailing wind direction from wind conditions."""
    if not wind_conditions or 'p_wd' not in wind_conditions or 'wd_bins' not in wind_conditions:
        return 0.0  # Default to north if no wind data
    
    p_wd = wind_conditions['p_wd']
    wd_bins = wind_conditions['wd_bins']
    
    # Find direction with highest probability
    max_prob_idx = np.argmax(p_wd)
    return wd_bins[max_prob_idx] if max_prob_idx < len(wd_bins) else 0.0

def rotate_coordinates(x: float, y: float, angle_deg: float) -> Tuple[float, float]:
    """Rotate coordinates by angle in degrees."""
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)

def meters_to_lat_lon(base_lat: float, base_lon: float, dx_m: float, dy_m: float) -> Tuple[float, float]:
    """Convert meters to latitude/longitude offsets from a base position."""
    lat_offset = dy_m / METERS_PER_LAT_DEGREE
    meters_per_lon_degree = METERS_PER_LAT_DEGREE * math.cos(math.radians(base_lat))
    lon_offset = dx_m / meters_per_lon_degree
    return (base_lat + lat_offset, base_lon + lon_offset)

def load_boundaries_geojson(project_id: str) -> Optional[dict]:
    """Load GeoJSON boundaries data."""
    try:
        file_path = load_file_from_storage(project_id, "boundaries.geojson", "terrain_agent")
        with open(file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        logger.info(f"Could not load boundaries: {e}")
        return None

def is_point_in_boundaries(lat: float, lon: float, boundaries_gdf: gpd.GeoDataFrame) -> bool:
    """Check if a point intersects with any boundary polygon."""
    point = Point(lon, lat)
    return any(point.intersects(geom) for geom in boundaries_gdf.geometry)

@tool
def create_grid_layout(
    project_id: str,
    center_lat: float,
    center_lon: float,
    num_turbines: int,
    turbine_model: str,
    rotor_diameter: float,
    capacity_mw: float,
    wind_angle: int,
    primary_spacing_d: float = 9.0,
    perpendicular_spacing_d: float = 3.0,
    auto_relocate: bool = True,
    search_radius_m: float = 1000
) -> dict:
    """
    Create a regular grid layout for wind turbines with elliptical spacing aligned to prevailing wind.
    This function generates a completely new layout using the provided coordinates as the center point.
    The layout uses different spacing in primary wind direction vs perpendicular to minimize wake effects.
    
    Args:
        project_id: Project identifier to load boundary constraints
        center_lat: Center latitude coordinate used as the center point for generating the grid layout
        center_lon: Center longitude coordinate used as the center point for generating the grid layout
        num_turbines: Target number of turbines to place
        turbine_model: Turbine model name
        rotor_diameter: Rotor diameter in meters
        capacity_mw: Turbine capacity in MW
        wind_angle: Prevailing wind direction in degrees for the location
        primary_spacing_d: Spacing in primary wind direction in rotor diameters (default: 9.0)
        perpendicular_spacing_d: Spacing perpendicular to wind direction in rotor diameters (default: 3.0)
        auto_relocate: Whether to automatically relocate conflicting turbines (default: True)
        search_radius_m: Search radius in meters for auto-relocation (default: 1000)
        
    Returns:
        Dict containing status, layout GeoJSON, and any skipped turbines
    """
    logger.info(f"create_grid_layout: project_id={project_id}, center=({center_lat}, {center_lon}), num_turbines={num_turbines}, turbine_model={turbine_model}, rotor_diameter={rotor_diameter}, capacity_mw={capacity_mw}, wind_angle={wind_angle}, primary_spacing_d={primary_spacing_d}, perpendicular_spacing_d={perpendicular_spacing_d}")
    try:
        auto_relocate = True

        # Elliptical spacing with configurable primary and perpendicular spacing
        spacing_primary_m = primary_spacing_d * rotor_diameter
        spacing_perpendicular_m = perpendicular_spacing_d * rotor_diameter
        
        # Load boundaries if available
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        # Calculate grid dimensions
        rows = int(math.sqrt(num_turbines))
        cols = math.ceil(num_turbines / rows)
        
        # Generate all turbine positions first (including conflicting ones)
        all_positions = []
        for row in range(rows):
            for col in range(cols):
                if len(all_positions) >= num_turbines:
                    break
                
                # Use elliptical spacing:
                x_m = (col - cols/2) * spacing_perpendicular_m
                y_m = (row - rows/2) * spacing_primary_m      
                
                x_m, y_m = rotate_coordinates(x_m, y_m, wind_angle)
                
                lat, lon = meters_to_lat_lon(center_lat, center_lon, x_m, y_m)
                all_positions.append((lat, lon))
        
        # Create initial layout with all positions
        features = []
        for i, (lat, lon) in enumerate(all_positions):
            features.append({
                "type": "Feature",
                "properties": {
                    "turbine_id": f"T{i+1}",
                    "turbine_model": turbine_model,
                    "capacity_MW": capacity_mw
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                }
            })
        
        if auto_relocate:
            initial_layout = {
                "type": "FeatureCollection",
                "features": features,
                "properties": {
                    "layout_type": "grid",
                    "total_capacity_MW": len(features) * capacity_mw,
                    "num_turbines": len(features),
                    "turbine_model": turbine_model
                }
            }
            
            relocation_result = relocate_conflicting_turbines(
                project_id, initial_layout, rotor_diameter, wind_angle, primary_spacing_d, perpendicular_spacing_d, search_radius_m
            )
            final_layout = relocation_result['layout'] if relocation_result['status'] == 'success' else initial_layout
            
            # Calculate center from actual turbine positions for map
            if final_layout.get('features'):
                lats = [f['geometry']['coordinates'][1] for f in final_layout['features']]
                lons = [f['geometry']['coordinates'][0] for f in final_layout['features']]
                map_center_lat = sum(lats) / len(lats)
                map_center_lon = sum(lons) / len(lons)
            else:
                map_center_lat, map_center_lon = center_lat, center_lon
            
            create_layout_map(project_id, final_layout, map_center_lat, map_center_lon, wind_angle=wind_angle)
            return relocation_result
        else:
            # Skip turbines in unbuildable areas
            valid_features = []
            skipped_turbines = []
            
            for feature in features:
                coords = feature['geometry']['coordinates']
                lon, lat = coords[0], coords[1]
                
                if boundaries_gdf is not None and is_point_in_boundaries(lat, lon, boundaries_gdf):
                    skipped_turbines.append({
                        "turbine_id": feature['properties']['turbine_id'],
                        "coordinates": [lat, lon],
                        "reason": "Located in unbuildable area"
                    })
                else:
                    valid_features.append(feature)
            
            final_layout = {
                "type": "FeatureCollection",
                "features": valid_features,
                "properties": {
                    "layout_type": "grid",
                    "total_capacity_MW": len(valid_features) * capacity_mw,
                    "num_turbines": len(valid_features),
                    "turbine_model": turbine_model
                }
            }
            
            # Calculate center from actual turbine positions for map
            if valid_features:
                lats = [f['geometry']['coordinates'][1] for f in valid_features]
                lons = [f['geometry']['coordinates'][0] for f in valid_features]
                map_center_lat = sum(lats) / len(lats)
                map_center_lon = sum(lons) / len(lons)
            else:
                map_center_lat, map_center_lon = center_lat, center_lon
            
            create_layout_map(project_id, final_layout, map_center_lat, map_center_lon, wind_angle=wind_angle)
            
            return {
                "status": "success",
                "layout": final_layout,
                "skipped_turbines": skipped_turbines,
                "summary": {
                    "requested_turbines": num_turbines,
                    "placed_turbines": len(valid_features),
                    "skipped_count": len(skipped_turbines)
                }
            }
        
    except Exception as e:
        logger.error(f"Error in create_grid_layout: {e}")
        return {"status": "error", "message": str(e)}

@tool
def create_offset_grid_layout(
    project_id: str,
    center_lat: float,
    center_lon: float,
    num_turbines: int,
    turbine_model: str,
    rotor_diameter: float,
    capacity_mw: float,
    wind_angle: int,
    primary_spacing_d: float = 9.0,
    perpendicular_spacing_d: float = 3.0,
    auto_relocate: bool = True,
    search_radius_m: float = 1000
) -> dict:
    """
    Create an offset grid layout for wind turbines with elliptical spacing and alternating row positions.
    This function generates a completely new layout using the provided coordinates as the center point.
    The offset grid reduces wake effects by staggering turbine positions with different spacing in wind directions.
    
    Args:
        project_id: Project identifier to load boundary constraints
        center_lat: Center latitude coordinate used as the center point for generating the offset grid layout
        center_lon: Center longitude coordinate used as the center point for generating the offset grid layout
        num_turbines: Target number of turbines to place
        turbine_model: Turbine model name
        rotor_diameter: Rotor diameter in meters
        capacity_mw: Turbine capacity in MW
        wind_angle: Prevailing wind direction in degrees for the location
        primary_spacing_d: Spacing in primary wind direction in rotor diameters (default: 9.0)
        perpendicular_spacing_d: Spacing perpendicular to wind direction in rotor diameters (default: 3.0)
        auto_relocate: Whether to automatically relocate conflicting turbines (default: True)
        search_radius_m: Search radius in meters for auto-relocation (default: 1000)
        
    Returns:
        Dict containing status, layout GeoJSON, and any skipped turbines
    """
    logger.info(f"create_offset_grid_layout: project_id={project_id}, center=({center_lat}, {center_lon}), num_turbines={num_turbines}, turbine_model={turbine_model}, rotor_diameter={rotor_diameter}, capacity_mw={capacity_mw}, wind_angle={wind_angle}, primary_spacing_d={primary_spacing_d}, perpendicular_spacing_d={perpendicular_spacing_d}")
    try:
        auto_relocate = True

        # Elliptical spacing with configurable primary and perpendicular spacing
        spacing_primary_m = primary_spacing_d * rotor_diameter
        spacing_perpendicular_m = perpendicular_spacing_d * rotor_diameter
        
        # Load boundaries if available
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        # Calculate grid dimensions
        rows = int(math.sqrt(num_turbines))
        cols = math.ceil(num_turbines / rows)
        
        # Generate all turbine positions first (including conflicting ones)
        all_positions = []
        for row in range(rows):
            for col in range(cols):
                if len(all_positions) >= num_turbines:
                    break
                # Use elliptical spacing:
                x_m = (col - cols/2) * spacing_perpendicular_m
                if row % 2 == 1:  # Offset odd rows by half primary spacing
                    x_m += spacing_perpendicular_m / 2
                y_m = (row - rows/2) * spacing_primary_m
                
                # Rotate based on wind direction
                x_m, y_m = rotate_coordinates(x_m, y_m, wind_angle)
                
                lat, lon = meters_to_lat_lon(center_lat, center_lon, x_m, y_m)
                all_positions.append((lat, lon))
        
        # Create initial layout with all positions
        features = []
        for i, (lat, lon) in enumerate(all_positions):
            features.append({
                "type": "Feature",
                "properties": {
                    "turbine_id": f"T{i+1}",
                    "turbine_model": turbine_model,
                    "capacity_MW": capacity_mw
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                }
            })
        
        if auto_relocate:
            initial_layout = {
                "type": "FeatureCollection",
                "features": features,
                "properties": {
                    "layout_type": "offset_grid",
                    "total_capacity_MW": len(features) * capacity_mw,
                    "num_turbines": len(features),
                    "turbine_model": turbine_model
                }
            }
            
            relocation_result = relocate_conflicting_turbines(
                project_id, initial_layout, rotor_diameter, wind_angle, primary_spacing_d, perpendicular_spacing_d, search_radius_m
            )
            final_layout = relocation_result['layout'] if relocation_result['status'] == 'success' else initial_layout
            
            # Calculate center from actual turbine positions for map
            if final_layout.get('features'):
                lats = [f['geometry']['coordinates'][1] for f in final_layout['features']]
                lons = [f['geometry']['coordinates'][0] for f in final_layout['features']]
                map_center_lat = sum(lats) / len(lats)
                map_center_lon = sum(lons) / len(lons)
            else:
                map_center_lat, map_center_lon = center_lat, center_lon
            
            create_layout_map(project_id, final_layout, map_center_lat, map_center_lon, wind_angle=wind_angle)
            return relocation_result
        else:
            # Skip turbines in unbuildable areas
            valid_features = []
            skipped_turbines = []
            
            for feature in features:
                coords = feature['geometry']['coordinates']
                lon, lat = coords[0], coords[1]
                
                if boundaries_gdf is not None and is_point_in_boundaries(lat, lon, boundaries_gdf):
                    skipped_turbines.append({
                        "turbine_id": feature['properties']['turbine_id'],
                        "coordinates": [lat, lon],
                        "reason": "Located in unbuildable area"
                    })
                else:
                    valid_features.append(feature)
            
            final_layout = {
                "type": "FeatureCollection",
                "features": valid_features,
                "properties": {
                    "layout_type": "offset_grid",
                    "total_capacity_MW": len(valid_features) * capacity_mw,
                    "num_turbines": len(valid_features),
                    "turbine_model": turbine_model
                }
            }
            
            # Calculate center from actual turbine positions for map
            if valid_features:
                lats = [f['geometry']['coordinates'][1] for f in valid_features]
                lons = [f['geometry']['coordinates'][0] for f in valid_features]
                map_center_lat = sum(lats) / len(lats)
                map_center_lon = sum(lons) / len(lons)
            else:
                map_center_lat, map_center_lon = center_lat, center_lon
            
            create_layout_map(project_id, final_layout, map_center_lat, map_center_lon, wind_angle=wind_angle)
            
            return {
                "status": "success",
                "layout": final_layout,
                "skipped_turbines": skipped_turbines,
                "summary": {
                    "requested_turbines": num_turbines,
                    "placed_turbines": len(valid_features),
                    "skipped_count": len(skipped_turbines)
                }
            }
        
    except Exception as e:
        logger.error(f"Error in create_offset_grid_layout: {e}")
        return {"status": "error", "message": str(e)}

@tool
def create_spiral_layout(
    project_id: str,
    center_lat: float,
    center_lon: float,
    num_turbines: int,
    turbine_model: str,
    rotor_diameter: float,
    capacity_mw: float,
    wind_angle: int,
    primary_spacing_d: float = 9.0,
    perpendicular_spacing_d: float = 3.0,
) -> dict:
    """
    Create a spiral layout for wind turbines with elliptical spacing using greedy distance-based placement.
    This function generates a completely new layout using the provided coordinates as the center point.
    Uses elliptical minimum distance validation to ensure proper turbine spacing based on wind direction.
    
    Args:
        project_id: Project identifier to load boundary constraints
        center_lat: Center latitude coordinate used as the starting center point for the spiral layout
        center_lon: Center longitude coordinate used as the starting center point for the spiral layout
        num_turbines: Target number of turbines to place
        turbine_model: Turbine model name
        rotor_diameter: Rotor diameter in meters
        capacity_mw: Turbine capacity in MW
        wind_angle: Prevailing wind direction in degrees for the location
        primary_spacing_d: Spacing in primary wind direction in rotor diameters (default: 9.0)
        perpendicular_spacing_d: Spacing perpendicular to wind direction in rotor diameters (default: 3.0)
        
    Returns:
        Dict containing status and layout GeoJSON with turbine positions
    """
    logger.info(f"create_spiral_layout: project_id={project_id}, center=({center_lat}, {center_lon}), num_turbines={num_turbines}, turbine_model={turbine_model}, rotor_diameter={rotor_diameter}, capacity_mw={capacity_mw}, wind_angle={wind_angle}, primary_spacing_d={primary_spacing_d}, perpendicular_spacing_d={perpendicular_spacing_d}")
    try:
        # Use minimum spacing for spiral generation (more restrictive spacing)
        min_spacing_m = min(primary_spacing_d, perpendicular_spacing_d) * rotor_diameter

        # Elliptical spacing with configurable primary and perpendicular spacing
        spacing_primary_m = primary_spacing_d * rotor_diameter
        spacing_perpendicular_m = perpendicular_spacing_d * rotor_diameter
        
        # Load boundaries if available
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        # Generate spiral path points
        spiral_points = []
        max_radius = min_spacing_m * num_turbines * 0.5  # Reasonable max radius
        angle = math.radians(wind_angle)
        radius = 0
        
        # Generate dense spiral path
        while radius <= max_radius:
            x_m = radius * math.cos(angle)
            y_m = radius * math.sin(angle)
            
            # Rotate coordinates to align with wind direction
            x_m_rot, y_m_rot = rotate_coordinates(x_m, y_m, wind_angle)
            lat, lon = meters_to_lat_lon(center_lat, center_lon, x_m_rot, y_m_rot)
            
            # Check boundaries
            if boundaries_gdf is None or not is_point_in_boundaries(lat, lon, boundaries_gdf):
                spiral_points.append((lat, lon, x_m_rot, y_m_rot, radius, angle))
            
            angle += 0.1  # Small angle increment for dense spiral
            radius += min_spacing_m * 0.02  # Small radius increment
        
        # Place turbines using greedy algorithm
        features = []
        placed_positions = []  # Store (x_m, y_m) for distance calculations
        
        # Start with center turbine if valid
        if boundaries_gdf is None or not is_point_in_boundaries(center_lat, center_lon, boundaries_gdf):
            features.append({
                "type": "Feature",
                "properties": {
                    "turbine_id": "T1",
                    "turbine_model": turbine_model,
                    "capacity_MW": capacity_mw
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [center_lon, center_lat]
                }
            })
            placed_positions.append((0, 0))
        
        # Place remaining turbines along spiral
        for lat, lon, x_m, y_m, radius, angle in spiral_points:
            if len(features) >= num_turbines:
                break
            
            # Check elliptical minimum distance to all placed turbines
            valid_position = True
            for placed_x, placed_y in placed_positions:
                # Calculate relative position vector
                dx = x_m - placed_x
                dy = y_m - placed_y
                
                # Rotate to wind-aligned coordinate system
                wind_rad = math.radians(wind_angle)
                dy_wind = dx * math.cos(-wind_rad) - dy * math.sin(-wind_rad)
                dx_wind = dx * math.sin(-wind_rad) + dy * math.cos(-wind_rad)
                
                # Check elliptical spacing constraint
                ellipse_constraint = (dx_wind / spacing_primary_m)**2 + (dy_wind / spacing_perpendicular_m)**2
                if ellipse_constraint < 1.0:
                    valid_position = False
                    break
            
            if valid_position:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "turbine_id": f"T{len(features)+1}",
                        "turbine_model": turbine_model,
                        "capacity_MW": capacity_mw
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    }
                })
                placed_positions.append((x_m, y_m))
        
        layout = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "layout_type": "spiral",
                "total_capacity_MW": len(features) * capacity_mw,
                "num_turbines": len(features),
                "turbine_model": turbine_model
            }
        }
        
        # Calculate center from actual turbine positions for map
        if features:
            lats = [f['geometry']['coordinates'][1] for f in features]
            lons = [f['geometry']['coordinates'][0] for f in features]
            map_center_lat = sum(lats) / len(lats)
            map_center_lon = sum(lons) / len(lons)
        else:
            map_center_lat, map_center_lon = center_lat, center_lon
        
        try:
            create_layout_map(project_id, layout, map_center_lat, map_center_lon, wind_angle=wind_angle)
        except Exception as e:
            logger.error(f"Failed to create final map: {e}")
        
        return {"status": "success", "layout": layout}
        
    except Exception as e:
        logger.error(f"Error in create_spiral_layout: {e}")
        return {"status": "error", "message": str(e)}

@tool
def create_greedy_layout(
    project_id: str,
    center_lat: float,
    center_lon: float,
    num_turbines: int,
    turbine_model: str,
    rotor_diameter: float,
    capacity_mw: float,
    wind_angle: int,
    primary_spacing_d: float = 9.0,
    perpendicular_spacing_d: float = 3.0,
    search_radius_m: float = 3000,
) -> dict:
    """
    Create an optimized greedy layout with elliptical spacing that places turbines in best available positions.
    This function generates a completely new layout using the provided coordinates as the center point.
    The greedy algorithm selects optimal positions considering distance to center and buildable areas.
    
    Args:
        project_id: Project identifier to load boundary constraints
        center_lat: Center latitude coordinate used as the center point for the search area
        center_lon: Center longitude coordinate used as the center point for the search area
        num_turbines: Target number of turbines to place
        turbine_model: Turbine model name
        rotor_diameter: Rotor diameter in meters
        capacity_mw: Turbine capacity in MW
        wind_angle: Location prevailing Wind Direction. Measured in degrees
        primary_spacing_d: Spacing in primary wind direction in rotor diameters (default: 9.0)
        perpendicular_spacing_d: Spacing perpendicular to wind direction in rotor diameters (default: 3.0)
        search_radius_m: Search radius in meters for candidate positions (default: 3000)
        
    Returns:
        Dict containing status and layout GeoJSON with turbine positions
    """
    logger.info(f"create_greedy_layout: project_id={project_id}, center=({center_lat}, {center_lon}), num_turbines={num_turbines}, turbine_model={turbine_model}, rotor_diameter={rotor_diameter}, capacity_mw={capacity_mw}, wind_angle={wind_angle}, primary_spacing_d={primary_spacing_d}, perpendicular_spacing_d={perpendicular_spacing_d}, search_radius_m={search_radius_m}")
    try:
        # Use minimum spacing for grid generation
        min_spacing_m = min(primary_spacing_d, perpendicular_spacing_d) * rotor_diameter
        
        # Load boundaries if available
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        features = []
        
        # Generate candidate positions in a grid within search radius
        candidates = []
        grid_spacing = min_spacing_m * 0.2  # Finer grid for more options

        steps = int(2 * search_radius_m / grid_spacing)
        for i in range(-steps//2, steps//2 + 1):
            for j in range(-steps//2, steps//2 + 1):
                x_m = i * grid_spacing
                y_m = j * grid_spacing
                distance_from_center = math.sqrt(x_m**2 + y_m**2)

                if distance_from_center <= search_radius_m:
                    # Rotate grid to align with wind direction
                    x_m_rotated, y_m_rotated = rotate_coordinates(x_m, y_m, wind_angle)
                    lat, lon = meters_to_lat_lon(center_lat, center_lon, x_m_rotated, y_m_rotated)
                    
                    # Check boundaries
                    if boundaries_gdf is None or not is_point_in_boundaries(lat, lon, boundaries_gdf):
                        candidates.append((lat, lon, distance_from_center, x_m_rotated, y_m_rotated))
        
        logger.info(f"Generated {len(candidates)} candidate positions within {search_radius_m}m radius")
                
        # Sort candidates by distance from center (closest first)
        candidates.sort(key=lambda x: x[2])
        
        # Calculate elliptical spacing parameters once
        primary_spacing_m = primary_spacing_d * rotor_diameter
        perpendicular_spacing_m = perpendicular_spacing_d * rotor_diameter
        
        # Expand outward from center, placing turbines that respect elliptical spacing
        for lat, lon, distance, x_m, y_m in candidates:
            if len(features) >= num_turbines:
                break
            
            # Check elliptical spacing with all existing turbines
            valid_position = True
            for placed_feature in features:
                placed_coords = placed_feature['geometry']['coordinates']
                placed_lon, placed_lat = placed_coords[0], placed_coords[1]
                
                # Calculate distance in meters using proper lat/lon to meters conversion
                meters_per_lat = 111320
                meters_per_lon = 111320 * math.cos(math.radians((lat + placed_lat) / 2))
                dx = (placed_lon - lon) * meters_per_lon
                dy = (placed_lat - lat) * meters_per_lat
                
                # Rotate to wind-aligned coordinate system
                wind_rad = math.radians(wind_angle)
                dy_wind = dx * math.cos(-wind_rad) - dy * math.sin(-wind_rad)
                dx_wind = dx * math.sin(-wind_rad) + dy * math.cos(-wind_rad)
                
                # Check elliptical spacing constraint
                ellipse_constraint = (dx_wind / primary_spacing_m)**2 + (dy_wind / perpendicular_spacing_m)**2
                if ellipse_constraint < 1.0:
                    valid_position = False
                    break
            
            if valid_position:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "turbine_id": f"T{len(features)+1}",
                        "turbine_model": turbine_model,
                        "capacity_MW": capacity_mw
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat]
                    }
                })
        
        layout = {
            "type": "FeatureCollection",
            "features": features,
            "properties": {
                "layout_type": "greedy",
                "total_capacity_MW": len(features) * capacity_mw,
                "num_turbines": len(features),
                "turbine_model": turbine_model
            }
        }
        
        # Calculate center from actual turbine positions for map
        if features:
            lats = [f['geometry']['coordinates'][1] for f in features]
            lons = [f['geometry']['coordinates'][0] for f in features]
            map_center_lat = sum(lats) / len(lats)
            map_center_lon = sum(lons) / len(lons)
        else:
            map_center_lat, map_center_lon = center_lat, center_lon
        
        # Create map automatically
        create_layout_map(project_id, layout, map_center_lat, map_center_lon, wind_angle=wind_angle)
        
        logger.info(f"Greedy layout completed: placed {len(features)}/{num_turbines} turbines")
        return {"status": "success", "layout": layout}
        
    except Exception as e:
        logger.error(f"Error in create_greedy_layout: {e}")
        return {"status": "error", "message": str(e)}
    
@tool
def explore_alternative_sites(
    project_id: str,
    center_lat: float,
    center_lon: float,
    num_turbines: int,
    turbine_model: str,
    rotor_diameter: float,
    capacity_mw: float,
    spacing_d: float = 9.0,
    search_radius_m: float = 5.0
) -> dict:
    """
    Explore alternative site locations around the initial center to find better placement areas.
    
    Args:
        project_id: Project identifier to load boundary constraints
        center_lat: Initial center latitude coordinate
        center_lon: Initial center longitude coordinate
        num_turbines: Target number of turbines to place
        turbine_model: Turbine model name
        rotor_diameter: Rotor diameter in meters
        capacity_mw: Turbine capacity in MW
        spacing_d: Spacing between turbines in rotor diameters (default: 9.0)
        search_radius_m: Search radius in kilometers for alternative centers (default: 5.0)
        
    Returns:
        Dict containing best alternative site location and expected turbine count
    """
    logger.info(f"explore_alternative_sites: project_id={project_id}, center=({center_lat}, {center_lon}), num_turbines={num_turbines}, turbine_model={turbine_model}, rotor_diameter={rotor_diameter}, capacity_mw={capacity_mw}, spacing_d={spacing_d}, search_radius_m={search_radius_m}")
    try:
        # Load boundaries if available
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        best_site = None
        best_score = 0
        spacing_m = spacing_d * rotor_diameter
        
        # Test alternative centers in a grid pattern
        search_radius_m = search_radius_m * 1000
        step_size_m = 1000  # Test centers every 1km
        steps = int(2 * search_radius_m / step_size_m)
        
        for i in range(-steps//2, steps//2 + 1):
            for j in range(-steps//2, steps//2 + 1):
                x_offset = i * step_size_m
                y_offset = j * step_size_m
                
                # Skip original center
                if x_offset == 0 and y_offset == 0:
                    continue
                    
                test_lat, test_lon = meters_to_lat_lon(center_lat, center_lon, x_offset, y_offset)
                
                # Create actual grid layout at this test center
                rows = int(math.sqrt(num_turbines))
                cols = math.ceil(num_turbines / rows)
                
                valid_turbines = 0
                for row in range(rows):
                    for col in range(cols):
                        if valid_turbines >= num_turbines:
                            break
                        x_m = (col - cols/2) * spacing_m
                        y_m = (row - rows/2) * spacing_m
                        turbine_lat, turbine_lon = meters_to_lat_lon(test_lat, test_lon, x_m, y_m)
                        
                        # Check if position is buildable
                        if boundaries_gdf is None or not is_point_in_boundaries(turbine_lat, turbine_lon, boundaries_gdf):
                            valid_turbines += 1
                
                # Score based on valid turbines and distance penalty
                distance_km = math.sqrt(x_offset**2 + y_offset**2) / 1000
                score = valid_turbines - distance_km * 0.5  # Penalty for distance
                
                if score > best_score:
                    best_score = score
                    best_site = {
                        "lat": test_lat,
                        "lon": test_lon,
                        "actual_turbines": valid_turbines,
                        "distance_from_original_km": distance_km
                    }
        
        if best_site and best_site["actual_turbines"] > 0:
            return {
                "status": "success",
                "message": f"Found better site {best_site['distance_from_original_km']:.1f}km away with {best_site['actual_turbines']} turbines",
                "alternative_site": best_site
            }
        else:
            return {
                "status": "warning",
                "message": "No better alternative sites found",
                "alternative_site": {
                    "lat": center_lat,
                    "lon": center_lon,
                    "actual_turbines": 0,
                    "distance_from_original_km": 0
                }
            }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@tool
def relocate_conflicting_turbines(
    project_id: str,
    layout: dict,
    rotor_diameter: float,
    wind_angle: int,
    primary_spacing_d: float = 9.0,
    perpendicular_spacing_d: float = 3.0,
    search_radius_m: float = 1000,
) -> dict:
    """
    Intelligently relocate turbines that are in unbuildable areas to nearby valid positions using elliptical spacing.
    
    Args:
        project_id: Project identifier to load boundary constraints
        layout: Existing turbine layout GeoJSON to optimize
        rotor_diameter: Rotor diameter in meters for spacing calculations
        wind_angle: Prevailing wind direction in degrees for the location
        primary_spacing_d: Spacing in primary wind direction in rotor diameters (default: 9.0)
        perpendicular_spacing_d: Spacing perpendicular to wind direction in rotor diameters (default: 3.0)
        search_radius_m: Search radius in meters for alternative positions (default: 1000)
        
    Returns:
        Dict containing status, optimized layout, and relocation summary
    """
    logger.info(f"relocate_conflicting_turbines: project_id={project_id}, rotor_diameter={rotor_diameter}, wind_angle={wind_angle}, primary_spacing_d={primary_spacing_d}, perpendicular_spacing_d={perpendicular_spacing_d}, search_radius_m={search_radius_m}, layout_turbines={len(layout.get('features', []))}")
    try:
        # Use minimum spacing for search grid generation
        min_spacing_m = min(primary_spacing_d, perpendicular_spacing_d) * rotor_diameter
        
        # Load boundaries if available
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        features = layout.get('features', [])
        optimized_features = []
        relocations = []
        removals = []
        
        # First pass: identify valid turbines and conflicting ones
        valid_turbines = []
        conflicting_turbines = []
        
        for feature in features:
            coords = feature['geometry']['coordinates']
            lon, lat = coords[0], coords[1]
            
            if boundaries_gdf is None or not is_point_in_boundaries(lat, lon, boundaries_gdf):
                valid_turbines.append(feature)
                optimized_features.append(feature)
            else:
                conflicting_turbines.append(feature)
        
        logger.info(f"Found {len(valid_turbines)} valid turbines and {len(conflicting_turbines)} conflicting turbines")
        
        # If no boundaries or no conflicts, return original layout
        if boundaries_gdf is None or len(conflicting_turbines) == 0:
            logger.info("No boundaries or no conflicts found, returning original layout")
            return {
                "status": "success",
                "layout": layout,
                "relocations": [],
                "removals": [],
                "summary": {
                    "original_turbines": len(features),
                    "final_turbines": len(features),
                    "relocated_count": 0,
                    "removed_count": 0
                }
            }
        
        # Second pass: try to relocate conflicting turbines
        for feature in conflicting_turbines:
            coords = feature['geometry']['coordinates']
            original_lon, original_lat = coords[0], coords[1]
            turbine_id = feature['properties']['turbine_id']
            
            # Search for alternative positions in a spiral pattern
            found_position = False
            
            # Generate candidate positions in concentric circles
            # step_size = max(20, int(min_spacing_m//10))  # distance between the circles
            step_size = 10  # distance between the circles
            for radius in range(step_size, int(search_radius_m), step_size):
                if found_position:
                    break
                    
                # Test positions around the circle
                num_positions = max(12, int(4 * math.pi * radius / step_size))
                for i in range(num_positions):
                    angle = 2 * math.pi * i / num_positions
                    x_offset = radius * math.cos(angle)
                    y_offset = radius * math.sin(angle)
                    
                    # Convert to lat/lon
                    meters_per_lat = 111320
                    meters_per_lon = 111320 * math.cos(math.radians(original_lat))
                    
                    new_lat = original_lat + y_offset / meters_per_lat
                    new_lon = original_lon + x_offset / meters_per_lon
                    
                    # Check if position is valid (not in boundaries)
                    if boundaries_gdf is not None and is_point_in_boundaries(new_lat, new_lon, boundaries_gdf):
                        continue
                    
                    # Check elliptical spacing with existing valid turbines
                    valid_spacing = True
                    for valid_feature in optimized_features:
                        valid_coords = valid_feature['geometry']['coordinates']
                        valid_lon, valid_lat = valid_coords[0], valid_coords[1]
                        
                        # Calculate relative position vector
                        dx = (new_lon - valid_lon) * meters_per_lon
                        dy = (new_lat - valid_lat) * meters_per_lat
                        
                        # Rotate to wind-aligned coordinate system
                        wind_rad = math.radians(wind_angle)
                        dx_wind = dx * math.cos(-wind_rad) - dy * math.sin(-wind_rad)
                        dy_wind = dx * math.sin(-wind_rad) + dy * math.cos(-wind_rad)
                        
                        # Check elliptical spacing constraint
                        primary_spacing_m = primary_spacing_d * rotor_diameter
                        perpendicular_spacing_m = perpendicular_spacing_d * rotor_diameter
                        
                        ellipse_constraint = (dx_wind / primary_spacing_m)**2 + (dy_wind / perpendicular_spacing_m)**2
                        if ellipse_constraint < 1.0:
                            valid_spacing = False
                            break
                    
                    if valid_spacing:
                        # Found a valid position
                        relocated_feature = {
                            "type": "Feature",
                            "properties": feature['properties'].copy(),
                            "geometry": {
                                "type": "Point",
                                "coordinates": [new_lon, new_lat]
                            }
                        }
                        optimized_features.append(relocated_feature)
                        relocations.append({
                            "turbine_id": turbine_id,
                            "original_position": [original_lon, original_lat],
                            "new_position": [new_lon, new_lat],
                            "distance_moved_m": radius
                        })
                        found_position = True
                        break
            
            if not found_position:
                removals.append({
                    "turbine_id": turbine_id,
                    "reason": "No valid alternative position found within search radius"
                })
        
        # Update layout
        optimized_layout = {
            "type": "FeatureCollection",
            "features": optimized_features,
            "properties": {
                **layout.get('properties', {}),
                "layout_type": f"{layout.get('properties', {}).get('layout_type', 'unknown')}_relocated",
                "num_turbines": len(optimized_features)
            }
        }
        
        # Calculate center for map
        if optimized_features:
            lats = [f['geometry']['coordinates'][1] for f in optimized_features]
            lons = [f['geometry']['coordinates'][0] for f in optimized_features]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            # create_layout_map(project_id, optimized_layout, center_lat, center_lon, wind_angle=wind_angle)
        
        return {
            "status": "success",
            "layout": optimized_layout,
            "relocations": relocations,
            "removals": removals,
            "summary": {
                "original_turbines": len(features),
                "final_turbines": len(optimized_features),
                "relocated_count": len(relocations),
                "removed_count": len(removals)
            }
        }
        
    except Exception as e:
        logger.error(f"Error in relocate_conflicting_turbines: {e}")
        return {"status": "error", "message": str(e)}

@tool
def relocate_turbines_manually(
    project_id: str,
    layout: dict,
    relocations: List[dict],
    wind_angle: int
) -> dict:
    """
    Manually relocate specific turbines using exact coordinates or directional moves.
    
    Args:
        project_id: Project identifier
        layout: Current turbine layout GeoJSON
        relocations: List of relocation instructions. Each item can be:
            - {"turbine_id": "T1", "new_lat": 35.067, "new_lon": -101.395}
            - {"turbine_id": "T2", "direction": "north", "distance_m": 200}
            - {"turbine_id": "T3", "direction": "northeast", "distance_m": 150}
            - {"turbine_id": "T4", "bearing_degrees": 45, "distance_m": 300}
        wind_angle: Prevailing wind direction in degrees for the location
        
    Returns:
        Dict containing status and updated layout with relocation summary
    """
    logger.info(f"relocate_turbines_manually: project_id={project_id}, layout_turbines={len(layout.get('features', []))}, relocations_count={len(relocations)}")
    try:
        # Load boundaries for validation
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        features = layout.get('features', [])
        updated_features = []
        relocation_results = []
        
        # Create lookup for turbines
        turbine_map = {f['properties']['turbine_id']: f for f in features}
        
        for relocation in relocations:
            turbine_id = relocation['turbine_id']
            
            if turbine_id not in turbine_map:
                relocation_results.append({
                    "turbine_id": turbine_id,
                    "status": "error",
                    "message": "Turbine not found"
                })
                continue
            
            feature = turbine_map[turbine_id].copy()
            original_coords = feature['geometry']['coordinates']
            original_lon, original_lat = original_coords[0], original_coords[1]
            
            # Calculate new position
            if 'new_lat' in relocation and 'new_lon' in relocation:
                # Exact coordinates provided
                new_lat = relocation['new_lat']
                new_lon = relocation['new_lon']
                
            elif 'direction' in relocation and 'distance_m' in relocation:
                # Directional move
                direction = relocation['direction'].lower()
                distance_m = relocation['distance_m']
                
                # Convert direction to bearing
                direction_map = {
                    'north': 0, 'northeast': 45, 'east': 90, 'southeast': 135,
                    'south': 180, 'southwest': 225, 'west': 270, 'northwest': 315
                }
                
                if direction in direction_map:
                    bearing = direction_map[direction]
                else:
                    relocation_results.append({
                        "turbine_id": turbine_id,
                        "status": "error",
                        "message": f"Unknown direction: {direction}"
                    })
                    continue
                
                # Calculate new position
                bearing_rad = math.radians(bearing)
                dx_m = distance_m * math.sin(bearing_rad)
                dy_m = distance_m * math.cos(bearing_rad)
                new_lat, new_lon = meters_to_lat_lon(original_lat, original_lon, dx_m, dy_m)
                
            elif 'bearing_degrees' in relocation and 'distance_m' in relocation:
                # Bearing and distance
                bearing = relocation['bearing_degrees']
                distance_m = relocation['distance_m']
                
                bearing_rad = math.radians(bearing)
                dx_m = distance_m * math.sin(bearing_rad)
                dy_m = distance_m * math.cos(bearing_rad)
                new_lat, new_lon = meters_to_lat_lon(original_lat, original_lon, dx_m, dy_m)
                
            else:
                relocation_results.append({
                    "turbine_id": turbine_id,
                    "status": "error",
                    "message": "Invalid relocation parameters"
                })
                continue
            
            # Validate new position
            if boundaries_gdf is not None and is_point_in_boundaries(new_lat, new_lon, boundaries_gdf):
                relocation_results.append({
                    "turbine_id": turbine_id,
                    "status": "warning",
                    "message": "New position is in unbuildable area",
                    "original_position": [original_lon, original_lat],
                    "attempted_position": [new_lon, new_lat]
                })
                # Keep original position
                updated_features.append(feature)
            else:
                # Update position
                feature['geometry']['coordinates'] = [new_lon, new_lat]
                updated_features.append(feature)
                relocation_results.append({
                    "turbine_id": turbine_id,
                    "status": "success",
                    "original_position": [original_lon, original_lat],
                    "new_position": [new_lon, new_lat],
                    "distance_moved_m": math.sqrt(
                        ((new_lon - original_lon) * 111320 * math.cos(math.radians(original_lat)))**2 +
                        ((new_lat - original_lat) * 111320)**2
                    )
                })
        
        # Add non-relocated turbines
        relocated_ids = {r['turbine_id'] for r in relocations}
        for feature in features:
            if feature['properties']['turbine_id'] not in relocated_ids:
                updated_features.append(feature)
        
        # Create updated layout
        updated_layout = {
            "type": "FeatureCollection",
            "features": updated_features,
            "properties": {
                **layout.get('properties', {}),
                "layout_type": f"{layout.get('properties', {}).get('layout_type', 'unknown')}_manually_adjusted",
                "num_turbines": len(updated_features)
            }
        }
        
        # Calculate center for map
        if updated_features:
            lats = [f['geometry']['coordinates'][1] for f in updated_features]
            lons = [f['geometry']['coordinates'][0] for f in updated_features]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            create_layout_map(project_id, updated_layout, center_lat, center_lon, wind_angle=wind_angle)
        
        return {
            "status": "success",
            "layout": updated_layout,
            "relocation_results": relocation_results,
            "summary": {
                "total_relocations_requested": len(relocations),
                "successful_relocations": len([r for r in relocation_results if r['status'] == 'success']),
                "failed_relocations": len([r for r in relocation_results if r['status'] in ['error', 'warning']])
            }
        }
        
    except Exception as e:
        logger.error(f"Error in relocate_turbines_manually: {e}")
        return {"status": "error", "message": str(e)}

@tool
def validate_layout(project_id: str, layout: dict, min_spacing_m: float = 1170) -> dict:
    """
    Validate turbine layout for boundary conflicts and minimum spacing violations.
    
    Args:
        project_id: Project identifier to load boundary constraints
        layout: Turbine layout GeoJSON to validate. Expected format:
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"turbine_id": "string","turbine_model": "string","capacity_MW": float},
                        "geometry": {"type": "Point", "coordinates": [-101.395, 35.067]}
                    }
                ]
            }
        min_spacing_m: Minimum spacing between turbines in meters (default: 1170m for 9D spacing)

    Returns:
        Dict with validation results, boundary/spacing violations, and all turbine distances
    """
    logger.info(f"validate_layout: project_id={project_id}, layout_turbines={len(layout.get('features', []))}, min_spacing_m={min_spacing_m}")
    try:
        features = layout.get('features', [])
        if not features:
            return {
                "status": "error",
                "validation_passed": False,
                "message": "No turbines found in layout",
                "boundary_violations": [],
                "spacing_violations": [],
                "turbine_distances": []
            }
        
        # Load boundaries
        boundaries = load_boundaries_geojson(project_id)
        boundaries_gdf = None
        if boundaries and boundaries.get('features'):
            boundaries_gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            boundaries_gdf.crs = 'EPSG:4326'
        
        boundary_violations = []
        spacing_violations = []
        turbine_positions = []
        
        # Extract positions and check boundary violations
        for feature in features:
            coords = feature['geometry']['coordinates']
            lon, lat = coords[0], coords[1]
            # Handle both 'turbine_id' and 'id' property names for compatibility
            turbine_id = feature['properties'].get('turbine_id')
            turbine_positions.append((turbine_id, lat, lon))
            
            # Check if turbine is in unbuildable area
            if boundaries_gdf is not None and is_point_in_boundaries(lat, lon, boundaries_gdf):
                boundary_violations.append({
                    "turbine_id": turbine_id,
                    "coordinates": [lat, lon],
                    "issue": "Located in unbuildable area (water, roads, buildings, or protected zone)"
                })
        
        # Check spacing violations and collect all distances
        turbine_distances = []
        for i, (id1, lat1, lon1) in enumerate(turbine_positions):
            for j, (id2, lat2, lon2) in enumerate(turbine_positions[i+1:], i+1):
                # Calculate distance
                meters_per_lat = 111320
                meters_per_lon = 111320 * math.cos(math.radians((lat1 + lat2) / 2))
                dx = (lon2 - lon1) * meters_per_lon
                dy = (lat2 - lat1) * meters_per_lat
                distance = math.sqrt(dx**2 + dy**2)
                
                turbine_distances.append({
                    "turbine1": id1,
                    "turbine2": id2,
                    "distance_m": round(distance, 1)
                })
                
                if distance < min_spacing_m:
                    spacing_violations.append({
                        "turbine1": id1,
                        "turbine2": id2,
                        "actual_distance_m": round(distance, 1),
                        "required_distance_m": min_spacing_m,
                        "shortfall_m": round(min_spacing_m - distance, 1)
                    })
        
        total_violations = len(boundary_violations) + len(spacing_violations)
        validation_passed = total_violations == 0
        
        return {
            "status": "success",
            "validation_passed": validation_passed,
            "total_turbines": len(features),
            "total_violations": total_violations,
            "boundary_violations": boundary_violations,
            "spacing_violations": spacing_violations,
            "turbine_distances": turbine_distances,
            "min_spacing_required_m": min_spacing_m,
            "spacing_validation_applied": True
        }
        
    except Exception as e:
        logger.error(f"Error in validate_layout: {e}")
        return {
            "status": "error",
            "validation_passed": False,
            "message": f"Validation failed: {str(e)}",
            "boundary_violations": [],
            "spacing_violations": [],
            "turbine_distances": []
        }

@tool
def save_layout(project_id: str, layout: dict, wind_angle: int) -> dict:
    """
    Save the final turbine layout GeoJSON to project storage and create final map visualization.
    
    Args:
        project_id: Project identifier for storage location
        layout: Complete turbine layout GeoJSON to save
        layout: Turbine layout GeoJSON to validate. Expected format:
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"turbine_id": "string","turbine_model": "string","capacity_MW": float},
                        "geometry": {"type": "Point", "coordinates": [-101.395, 35.067]}
                    }
                ]
            }
        wind_angle: Prevailing wind direction in degrees for the location
        
    Returns:
        Dict containing save status and storage information
    """
    logger.info(f"save_layout: project_id={project_id}, layout_turbines={len(layout.get('features', []))}")
    try:
        result = save_file_with_storage(
            json.dumps(layout, indent=2),
            project_id,
            "turbine_layout.geojson",
            "text",
            "layout_agent"
        )
        
        # Create final layout map
        if layout.get('features'):
            lats = [f['geometry']['coordinates'][1] for f in layout['features']]
            lons = [f['geometry']['coordinates'][0] for f in layout['features']]
            center_lat = sum(lats) / len(lats)
            center_lon = sum(lons) / len(lons)
            create_layout_map(project_id, layout, center_lat, center_lon, wind_angle=wind_angle, final_map=True)
        
        return {
            "status": "success",
            "message": "Layout saved successfully with final map",
            "project_id": project_id,
            **result
        }
        
    except Exception as e:
        logger.error(f"Error in save_layout: {e}")
        return {"status": "error", "message": str(e)}

@tool
def create_layout_map(
    project_id: str,
    layout: dict,
    center_lat: float,
    center_lon: float,
    radius_m: int = 2000,
    wind_angle: float = None,
    final_map: bool = False
) -> dict:
    """
    Create and save a satellite map visualization showing turbine positions and boundary constraints.
    
    Args:
        project_id: Project identifier for loading boundaries and saving map
        layout: Turbine layout GeoJSON to visualize
        center_lat: Center latitude for map extent
        center_lon: Center longitude for map extent
        radius_m: Map radius in meters (default: 2,000)
        
    Returns:
        Dict containing map creation status and image data
    """
    logger.info(f"create_layout_map: project_id={project_id}, center=({center_lat}, {center_lon}), radius_m={radius_m}, wind_angle={wind_angle}, layout_turbines={len(layout.get('features', []))}")
    try:
        # Calculate optimal radius based on layout extent
        features = layout.get('features', [])
        if features:
            lats = [f['geometry']['coordinates'][1] for f in features]
            lons = [f['geometry']['coordinates'][0] for f in features]
            
            # Calculate layout extent
            lat_range = max(lats) - min(lats)
            lon_range = max(lons) - min(lons)
            
            # Convert to meters and add padding
            meters_per_degree = 111319.9
            lat_extent_m = lat_range * meters_per_degree
            lon_extent_m = lon_range * meters_per_degree * abs(math.cos(math.radians(center_lat)))
            
            # Use the larger extent plus padding, with minimum of 1000m
            calculated_radius = max(lat_extent_m, lon_extent_m) * 0.6 + 500
            radius_m = max(calculated_radius, 1000)
        
        # Get satellite imagery
        meters_per_degree = 111319.9
        radius_deg_lat = radius_m / meters_per_degree
        radius_deg_lon = radius_m / (meters_per_degree * abs(math.cos(math.radians(center_lat))))
        
        bbox_west = center_lon - radius_deg_lon
        bbox_east = center_lon + radius_deg_lon
        bbox_south = center_lat - radius_deg_lat
        bbox_north = center_lat + radius_deg_lat
        
        # Get satellite imagery from USGS using Web Mercator
        service_url = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/export"
        params = {
            'bbox': f'{bbox_west},{bbox_south},{bbox_east},{bbox_north}',
            'bboxSR': '4326',
            'imageSR': '3857',  # Request in Web Mercator
            'size': '1024,1024',
            'format': 'png',
            'f': 'image'
        }
        
        response = requests.get(service_url, params=params, timeout=30)
        
        if response.status_code != 200:
            return {"status": "error", "message": "Failed to retrieve satellite imagery"}
        
        # Create map with Web Mercator projection
        base_image = Image.open(io.BytesIO(response.content))
        if base_image.mode in ('RGBA', 'LA'):
            base_image = base_image.convert('RGB')
        
        # Convert bbox to Web Mercator
        from pyproj import Transformer
        transformer = Transformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)
        west_3857, south_3857 = transformer.transform(bbox_west, bbox_south)
        east_3857, north_3857 = transformer.transform(bbox_east, bbox_north)
        
        fig, ax = plt.subplots(figsize=(8, 6))
        extent_3857 = [west_3857, east_3857, south_3857, north_3857]
        ax.imshow(base_image, extent=extent_3857, aspect='equal')
        
        # Load and overlay boundaries in Web Mercator
        boundaries = load_boundaries_geojson(project_id)
        if boundaries and boundaries.get('features'):
            gdf = gpd.GeoDataFrame.from_features(boundaries['features'])
            gdf.crs = 'EPSG:4326'
            gdf = gdf.to_crs('EPSG:3857')
            
            if 'feature_type' in gdf.columns:
                for feature_type in gdf['feature_type'].unique():
                    subset = gdf[gdf['feature_type'] == feature_type]
                    if feature_type == 'water':
                        subset.plot(ax=ax, color='blue', alpha=0.6, edgecolor='darkblue', linewidth=1)
                    elif feature_type == 'roads':
                        subset.plot(ax=ax, color='orange', alpha=0.6, edgecolor='darkorange', linewidth=1)
                    elif feature_type == 'buildings':
                        subset.plot(ax=ax, color='red', alpha=0.6, edgecolor='darkred', linewidth=1)
                    else:
                        subset.plot(ax=ax, color='purple', alpha=0.6, edgecolor='darkviolet', linewidth=1)
            else:
                gdf.plot(ax=ax, color='purple', alpha=0.6, edgecolor='darkviolet', linewidth=1)
        
        # Convert turbine coordinates to Web Mercator
        turbine_coords_3857 = []
        for feature in features:
            lon, lat = feature['geometry']['coordinates']
            x_3857, y_3857 = transformer.transform(lon, lat)
            turbine_coords_3857.append((x_3857, y_3857, feature))
        
        # Overlay turbines using Web Mercator coordinates
        for x_3857, y_3857, feature in turbine_coords_3857:
            turbine_id = feature['properties']['turbine_id']
            
            # Plot turbine as white pin using Web Mercator coordinates
            ax.scatter(x_3857, y_3857, c='white', s=100, marker='o', 
                      linewidths=2, edgecolors='black', zorder=10, alpha=0.9)
            
            # Add turbine ID label
            ax.annotate(turbine_id, (x_3857, y_3857), 
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=8, fontweight='bold', color='white',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.7),
                       zorder=11)
            
        # Add wind rose in bottom right corner
        if wind_angle is not None:
            rose_center = (0.92, 0.1)
            rose_radius = 0.04
            
            # Draw black circle
            circle = plt.Circle(rose_center, rose_radius, transform=ax.transAxes,
                              fill=False, color='black', linewidth=2, zorder=15)
            ax.add_patch(circle)

            # Draw wind direction arrow with better visibility
            wind_rad = math.radians(wind_angle)
            arrow_start_x = rose_center[0] + (rose_radius * 0.1) * math.sin(wind_rad)
            arrow_start_y = rose_center[1] + (rose_radius * 0.1) * math.cos(wind_rad)
            arrow_end_x = rose_center[0] + (rose_radius * 0.85) * math.sin(wind_rad)
            arrow_end_y = rose_center[1] + (rose_radius * 0.85) * math.cos(wind_rad)

            ax.annotate('', xy=(arrow_end_x, arrow_end_y), xytext=(arrow_start_x, arrow_start_y),
                       xycoords='axes fraction', textcoords='axes fraction',
                       arrowprops=dict(arrowstyle='-', color='red', lw=3), zorder=16)
            
            # Add cardinal direction indicators outside circle
            directions = [(0, 'N'), (90, 'E'), (180, 'S'), (270, 'W')]
            for dir_angle, label in directions:
                rad = math.radians(dir_angle)
                label_x = rose_center[0] + (rose_radius * 1.35) * math.sin(rad)
                label_y = rose_center[1] + (rose_radius * 1.35) * math.cos(rad)
                ax.text(label_x, label_y, label,
                       ha='center', va='center', fontsize=6, color='black',
                       transform=ax.transAxes, zorder=17)
            
            # Add wind angle text below circle
            ax.text(rose_center[0], rose_center[1] - rose_radius * 2.0, f'Wind: {wind_angle}°',
                   ha='center', va='center', fontsize=7, color='white',
                   bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.8),
                   transform=ax.transAxes, zorder=17)
        
        # Set title and format
        layout_type = layout.get('properties', {}).get('layout_type', 'Wind Farm')
        num_turbines = len(features)
        ax.set_title(f'{layout_type.title()} Layout - {num_turbines} Turbines', fontsize=12)
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')
        ax.set_xlim(extent_3857[0], extent_3857[1])
        ax.set_ylim(extent_3857[2], extent_3857[3])
        ax.set_aspect('equal')
        
        # Format axis labels to show lat/lon instead of Web Mercator meters
        ax.tick_params(axis='both', which='major', labelsize=8)
        
        # Convert Web Mercator tick labels back to lat/lon for readability
        def format_lon(x, p):
            lon, _ = transformer.transform(x, extent_3857[2], direction='INVERSE')
            return f'{lon:.3f}'
        
        def format_lat(y, p):
            _, lat = transformer.transform(extent_3857[0], y, direction='INVERSE')
            return f'{lat:.3f}'
        
        ax.xaxis.set_major_formatter(plt.FuncFormatter(format_lon))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(format_lat))
        
        # Save map
        if final_map:
            filename = "layout_final.png"
        else:
            image_id = get_next_image_id(project_id, "layout_map")
            filename = f"layout_map_{image_id}.png"
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=250, bbox_inches='tight', facecolor='white')
            temp_filepath = temp_file.name
        
        save_file_with_storage(
            temp_filepath,
            project_id,
            filename,
            "file_copy",
            "layout_agent"
        )
        
        os.unlink(temp_filepath)
        
        # Return image as bytes
        buffer = io.BytesIO()
        plt.savefig(buffer, format='PNG', dpi=250, bbox_inches='tight', facecolor='white')
        plt.close()
        
        return {
            "status": "success",
            "message": f"Layout map saved as {filename}",
            "image_id": image_id if not final_map else None,
            "content": [{
                "image": {
                    "format": "png",
                    "source": {
                        "bytes": buffer.getvalue()
                    }
                }
            }]
        }
        
    except Exception as e:
        logger.error(f"Error in create_layout_map: {e}")
        return {"status": "error", "message": str(e)}

@tool
def load_turbine_layout(project_id: str) -> dict:
    """
    Load an existing turbine layout GeoJSON from project storage.
    
    Args:
        project_id: Project identifier for loading the layout
        
    Returns:
        Dict containing layout data or error message if not found
    """
    logger.info(f"load_turbine_layout: project_id={project_id}")
    try:
        file_path = load_file_from_storage(project_id, "turbine_layout.geojson", "layout_agent")
        
        with open(file_path, 'r') as file:
            layout = json.load(file)
        
        # Validate layout structure
        if not layout.get('type') == 'FeatureCollection':
            return {
                "status": "error",
                "message": "Invalid layout format: not a FeatureCollection"
            }
        
        features = layout.get('features', [])
        if not features:
            return {
                "status": "warning",
                "message": "Layout loaded but contains no turbines",
                "layout": layout
            }
        
        return {
            "status": "success",
            "message": f"Layout loaded successfully with {len(features)} turbines",
            "layout": layout,
            "summary": {
                "num_turbines": len(features),
                "layout_type": layout.get('properties', {}).get('layout_type', 'unknown'),
                "total_capacity_MW": layout.get('properties', {}).get('total_capacity_MW', 0),
                "turbine_model": layout.get('properties', {}).get('turbine_model', 'unknown')
            }
        }
        
    except FileNotFoundError:
        logger.error(f"Layout file not found for project {project_id}")
        return {
            "status": "error",
            "message": f"No turbine layout found for project {project_id}. Create a layout first using one of the layout creation tools."
        }
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON for project {project_id}")
        return {
            "status": "error",
            "message": "Layout file is corrupted or not valid JSON"
        }
    except Exception as e:
        logger.error(f"Error loading layout for project {project_id}: {e}")
        return {
            "status": "error",
            "message": f"Failed to load layout: {str(e)}"
        }

@tool
def load_layout_image(
    project_id: str,
    image_id: Optional[int] = None
) -> dict:
    """
    Load and display the most recent or specific layout map image for visual validation.
    
    Args:
        project_id: Project identifier for loading the layout image
        image_id: Optional specific image ID to load (loads most recent if not provided)
        
    Returns:
        Dict containing image data for agent visual inspection
    """
    logger.info(f"load_layout_image: project_id={project_id}, image_id={image_id}")
    try:
        # If no image_id provided, get the most recent one
        if image_id is None:
            # Get current counter value (most recent)
            key = f"{project_id}_layout_map"
            image_id = _image_counter.get(key, 1)
        
        filename = f"layout_map_{image_id}.png"
        
        # Load image from storage
        try:
            file_path = load_file_from_storage(project_id, filename, "layout_agent")
            
            # Read image as bytes
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            
            return {
                "status": "success",
                "message": f"Loaded layout map {filename} for visual validation",
                "image_id": image_id,
                "content": [{
                    "image": {
                        "format": "png",
                        "source": {
                            "bytes": image_bytes
                        }
                    }
                }]
            }
            
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"Layout map {filename} not found. Create a layout map first using create_layout_map."
            }
        
    except Exception as e:
        logger.error(f"Error loading layout image for project {project_id}: {e}")
        return {"status": "error", "message": str(e)}