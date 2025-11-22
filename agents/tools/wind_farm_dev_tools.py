import json
import logging
import math

from datetime import datetime
from strands import tool
from typing import Dict, Any
import geopandas as gpd
from shapely.geometry import Point
from .shared_tools import list_project_files, load_file_from_storage

logger = logging.getLogger(__name__)

@tool
def generate_project_id() -> dict:
    """
    Generate a unique project ID for a new wind farm project.
    
    This tool creates a unique identifier that should be used consistently throughout
    a single project's analysis workflow. Generate a new ID only when starting a
    completely new project, location, or wind farm analysis.
    
    Returns:
        dict: Contains the generated unique project ID
            - project_id (str): unique identifier for the project
            - message (str): Confirmation message
    """
    logger.info("Generating new project ID")
    
    try:
        project_id = datetime.now().strftime("%y%m%d_%H%M%S")
        logger.info(f"Generated project ID: {project_id}")
        return {
            "project_id": project_id,
            "message": f"Generated new project ID: {project_id}"
        }
    except Exception as e:
        logger.error(f"Failed to generate project ID: {e}")
        return {
            "error": f"Failed to generate project ID: {str(e)}"
        }

@tool
def validate_layout_quality(project_id: str, min_spacing_m: float = 300) -> Dict[str, Any]:
    """
    Validate turbine layout for boundary conflicts and minimum spacing violations.
    Loads layout and boundaries from project files and validates placement quality.
    
    Args:
        project_id (str): Project identifier to load layout and boundary data
        min_spacing_m (float): Minimum spacing between turbines in meters
        
    Returns:
        Dict with validation results, boundary/spacing violations, and all turbine distances
    """
    logger.info(f"Validating layout quality for project: {project_id}, min_spacing_m={min_spacing_m}")
    
    try:
        # Load layout data
        try:
            file_path = load_file_from_storage(project_id, "turbine_layout.geojson", "layout_agent")
            with open(file_path, 'r') as file:
                layout = json.load(file)
        except FileNotFoundError:
            return {
                "status": "error",
                "validation_passed": False,
                "message": f"No turbine layout found for project {project_id}. Create a layout first.",
                "boundary_violations": [],
                "spacing_violations": [],
                "turbine_distances": []
            }
        
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
        
        # Load boundaries (optional)
        boundaries = None
        try:
            file_path = load_file_from_storage(project_id, "boundaries.geojson", "terrain_agent")
            with open(file_path, 'r') as file:
                boundaries = json.load(file)
        except FileNotFoundError:
            logger.info(f"No boundaries file found for project {project_id} - skipping boundary validation")
        
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
            turbine_id = feature['properties'].get('turbine_id')
            turbine_positions.append((turbine_id, lat, lon))
            
            # Check if turbine is in unbuildable area
            if boundaries_gdf is not None:
                point = Point(lon, lat)
                if any(point.intersects(geom) for geom in boundaries_gdf.geometry):
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
        logger.error(f"Error validating layout: {e}")
        return {
            "status": "error",
            "validation_passed": False,
            "message": f"Validation failed: {str(e)}",
            "boundary_violations": [],
            "spacing_violations": [],
            "turbine_distances": []
        }

@tool
def get_project_status(project_id: str) -> Dict[str, Any]:
    """
    Get the current status of a wind farm development project.
    
    Args:
        project_id (str): unique project identifier
        
    Returns:
        Dict containing project status and completion progress
    """
    logger.info(f"Getting project status for: {project_id}")
    
    try:
        logger.info(f"Listing project files for status check")
        files = list_project_files(project_id)
        if not files['success']:
            logger.warning(f"Failed to list project files: {files.get('error', 'Unknown error')}")
            return files
        
        status = {
            'terrain_analysis': False,
            'layout_design': False,
            'simulation': False,
            'reporting': False,
            'completion_percentage': 0
        }
        
        # Check each stage based on file patterns
        all_files = files['files']['all_files']
        logger.info(f"Found {len(all_files)} total files for project {project_id}")
        
        # Check for terrain analysis files
        if any('terrain_agent' in f for f in all_files):
            status['terrain_analysis'] = True
        
        # Check for layout design files
        if any('layout_agent' in f for f in all_files):
            status['layout_design'] = True
        
        # Check for simulation files
        if any('simulation_agent' in f for f in all_files):
            status['simulation'] = True
        
        # Check for report files
        if any('report_agent' in f for f in all_files):
            status['reporting'] = True
        
        # Calculate completion percentage
        completed_stages = sum([
            status['terrain_analysis'],
            status['layout_design'], 
            status['simulation'],
            status['reporting']
        ])
        status['completion_percentage'] = (completed_stages / 4) * 100
        
        # Determine next step
        if not status['terrain_analysis']:
            next_step = "Run terrain analysis to identify unbuildable areas"
        elif not status['layout_design']:
            next_step = "Create turbine layout design"
        elif not status['simulation']:
            next_step = "Run wake simulation and energy calculations"
        elif not status['reporting']:
            next_step = "Generate executive report"
        else:
            next_step = "Project complete - all stages finished"
        
        return {
            'success': True,
            'project_id': project_id,
            'status': status,
            'next_step': next_step,
            'total_files': len(all_files),
            'message': f"Project {status['completion_percentage']:.0f}% complete"
        }
        
    except Exception as e:
        logger.error(f"Error getting project status: {e}")
        return {
            'success': False,
            'error': f"Failed to get project status: {str(e)}"
        }
    
@tool
def load_layout_image(
    project_id: str
) -> dict:
    """
    Load and display the most recent or specific layout map image for visual validation.
    
    Args:
        project_id: Project identifier for loading the layout image
        
    Returns:
        Dict containing image data for agent visual inspection
    """
    logger.info(f"load_layout_image: project_id={project_id}")
    try:
        filename = f"layout_final.png"
        
        # Load image from storage
        try:
            file_path = load_file_from_storage(project_id, filename, "layout_agent")
            
            # Read image as bytes
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            
            return {
                "status": "success",
                "message": f"Loaded layout map {filename} for visual validation",
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
                "message": f"Layout map {filename} not found. Create a layout first."
            }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
