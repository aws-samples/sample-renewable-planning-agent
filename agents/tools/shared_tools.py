
from strands import tool
import json
import os
import logging
import re
from typing import Dict, List, Any
from .storage_utils import get_s3_config, load_file_from_storage
import boto3
from turbine_models.parser import Turbines
from difflib import get_close_matches

logger = logging.getLogger(__name__)

@tool
def get_turbine_specs(turbine_model: str) -> Dict[str, Any]:
    """
    Retrieve turbine specifications with fuzzy matching for closest name.
    Args:
        turbine_model: Turbine model name to search for
    Returns:
        Dictionary of the closest matching turbine or default if none are close
    """
    
    default_turbine_name = 'IEA_Reference_3.4MW_130'
    turbs = Turbines()
    
    # Try exact match first
    turbine_specs = turbs.specs(turbine_model)
    if turbine_specs:
        logger.info(f"Exact match found for turbine: {turbine_model}")
        return turbine_specs
    
    # Get all available turbine names
    turbine_type = "onshore"
    onshore_turbs = turbs.turbines(group=turbine_type)
    all_turbines = list(onshore_turbs.values())
    
    # Find closest matches
    close_matches = get_close_matches(turbine_model, all_turbines, n=1, cutoff=0.6)
    
    if close_matches:
        closest_match = close_matches[0]
        logger.info(f"Close match found: '{closest_match}' for requested '{turbine_model}'")
        return turbs.specs(closest_match)
    else:
        logger.warning(f"No close match found for '{turbine_model}'. Using default: {default_turbine_name}")
        return turbs.specs(default_turbine_name)

@tool
def list_project_files(project_id: str) -> Dict[str, Any]:
    """
    List all files available for a specific project ID.
    
    Args:
        project_id (str): unique project identifier
        
    Returns:
        Dict containing lists of available files by type
    """
    logger.info(f"Listing files for project: {project_id}")
    try:
        s3_config = get_s3_config()
        use_s3_storage = s3_config['use_s3'] and s3_config['bucket_name']
        logger.info(f"Using {'S3' if use_s3_storage else 'local'} storage for project {project_id}")
        
        files_found = {
            'images': [],
            'data_files': [],
            'maps': [],
            'charts': [],
            'layouts': [],
            'all_files': []
        }
        
        if use_s3_storage:
            # List S3 objects
            s3 = boto3.client('s3')
            
            try:
                response = s3.list_objects_v2(
                    Bucket=s3_config['bucket_name'],
                    Prefix=f"{project_id}/"
                )
                
                if 'Contents' in response:
                    for obj in response['Contents']:
                        full_path = obj['Key'].replace(f"{project_id}/", "")
                        if full_path and '/' in full_path:  # Skip empty and root-level files
                            files_found['all_files'].append(full_path)
                            
                            filename = os.path.basename(full_path)
                            # Categorize files
                            if filename.endswith(('.png', '.jpg', '.jpeg')):
                                files_found['images'].append(full_path)
                                if 'map' in filename.lower():
                                    files_found['maps'].append(full_path)
                                elif any(chart_type in filename.lower() for chart_type in ['chart', 'aep', 'wake', 'wind', 'power']):
                                    files_found['charts'].append(full_path)
                            elif filename.endswith(('.geojson', '.json')):
                                files_found['data_files'].append(full_path)
                                if 'layout' in filename.lower():
                                    files_found['layouts'].append(full_path)
                            elif filename.endswith(('.csv', '.txt')):
                                files_found['data_files'].append(full_path)
                                
            except Exception as e:
                logger.error(f"Error listing S3 objects: {e}")
                
        else:
            # List local files
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            project_dir = os.path.join(project_root, "assets", project_id)
            
            if os.path.exists(project_dir):
                logger.info(f"Scanning local project directory: {project_dir}")
                for agent_folder in os.listdir(project_dir):
                    agent_path = os.path.join(project_dir, agent_folder)
                    if os.path.isdir(agent_path):
                        logger.info(f"Scanning agent folder: {agent_folder}")
                        for filename in os.listdir(agent_path):
                            if os.path.isfile(os.path.join(agent_path, filename)):
                                full_path = f"{agent_folder}/{filename}"
                                files_found['all_files'].append(full_path)
                                
                                # Categorize files
                                if filename.endswith(('.png', '.jpg', '.jpeg')):
                                    files_found['images'].append(full_path)
                                    if 'map' in filename.lower():
                                        files_found['maps'].append(full_path)
                                    elif any(chart_type in filename.lower() for chart_type in ['chart', 'aep', 'wake', 'wind', 'power']):
                                        files_found['charts'].append(full_path)
                                elif filename.endswith(('.geojson', '.json')):
                                    files_found['data_files'].append(full_path)
                                    if 'layout' in filename.lower():
                                        files_found['layouts'].append(full_path)
                                elif filename.endswith(('.csv', '.txt')):
                                    files_found['data_files'].append(full_path)
        
        # Sort files and find latest maps by image_id
        for category in files_found:
            files_found[category].sort()
            
        # Find latest map files (highest image_id)
        latest_maps = {}
        for map_file in files_found['maps']:
            # Extract map type and image_id from filename only
            filename = os.path.basename(map_file)
            match = re.search(r'(\w+)_map_(\d+)\.png', filename)
            if match:
                map_type = match.group(1)
                image_id = int(match.group(2))
                if map_type not in latest_maps or image_id > latest_maps[map_type]['image_id']:
                    latest_maps[map_type] = {'filename': map_file, 'image_id': image_id}
        
        files_found['latest_maps'] = {k: v['filename'] for k, v in latest_maps.items()}
        
        logger.info(f"Listed {len(files_found['all_files'])} files: {files_found['all_files']}")
        
        return {
            'success': True,
            'project_id': project_id,
            'files': files_found,
            'total_files': len(files_found['all_files']),
            'message': f"Found {len(files_found['all_files'])} files for project {project_id}"
        }
        
    except Exception as e:
        logger.error(f"Error listing project files: {e}")
        return {
            'success': False,
            'error': f"Failed to list project files: {str(e)}"
        }

@tool
def load_project_data(project_id: str, filename: str, agent_folder: str = None) -> Dict[str, Any]:
    """
    Load data from a specific project file.
    
    Args:
        project_id (str): unique project identifier
        filename (str): Name of the file to load
        agent_folder (str): Agent-specific folder (e.g., 'terrain_agent', 'layout_agent')
        
    Returns:
        Dict containing the file content and metadata
    """
    logger.info(f"Loading project data: {project_id}/{filename} from {agent_folder}")
    try:
        # Determine content type based on file extension
        if filename.endswith(('.json', '.geojson')):
            logger.info(f"Loading JSON file: {filename} from storage")
            file_path = load_file_from_storage(project_id, filename, agent_folder)
            logger.info(f"File path resolved to: {file_path}")
            with open(file_path, 'r') as file:
                data = json.load(file)
            logger.info(f"Successfully loaded JSON data with {len(str(data))} characters")
            return {
                'success': True,
                'filename': filename,
                'content_type': 'json',
                'data': data,
                'message': f"Successfully loaded JSON data from {filename}"
            }
        elif filename.endswith(('.csv', '.txt')):
            if filename == "raw_output_data.csv": 
                return {
                'success': False,
                'filename': filename,
                'content_type': 'csv',
                'data': None,
                'message': f"Don't load raw data {filename}"
            }
            file_path = load_file_from_storage(project_id, filename, agent_folder)
            with open(file_path, 'r') as file:
                content = file.read()
            return {
                'success': True,
                'filename': filename,
                'content_type': 'text',
                'data': content,
                'message': f"Successfully loaded text data from {filename}"
            }
        elif filename.endswith(('.png', '.jpg', '.jpeg')):
            # For images, just return metadata
            return {
                'success': True,
                'filename': filename,
                'content_type': 'image',
                'data': None,
                'message': f"Image file {filename} is available for reference in reports"
            }
        else:
            return {
                'success': False,
                'error': f"Unsupported file type: {filename}"
            }
            
    except Exception as e:
        logger.error(f"Error loading project data: {e}")
        return {
            'success': False,
            'error': f"Failed to load {filename}: {str(e)}"
        }

@tool
def get_latest_images(project_id: str, image_types: List[str] = None) -> Dict[str, Any]:
    """
    Get the latest images for a project, particularly useful for maps with image_id.
    
    Args:
        project_id (str): unique project identifier
        image_types (List[str]): Optional list of image types to filter (e.g., ['layout_map', 'terrain_map'])
        
    Returns:
        Dict containing the latest images found
    """
    logger.info(f"Getting latest images for project: {project_id}")
    try:
        # First get all project files
        logger.info(f"Getting all project files to find latest images")
        files_result = list_project_files(project_id)
        
        if not files_result['success']:
            logger.warning(f"Failed to get project files: {files_result.get('error', 'Unknown error')}")
            return files_result
        
        all_images = files_result['files']['images']
        logger.info(f"Found {len(all_images)} total images to process")
        latest_images = {}
        
        # Process each image to find latest versions
        for image_file in all_images:
            # Extract filename from full path for pattern matching
            filename = os.path.basename(image_file)
            # Check for images with image_id pattern (e.g., layout_map_1.png, terrain_map_2.png)
            match = re.search(r'(\w+_map)_(\d+)\.png', filename)
            if match:
                image_type = match.group(1)
                image_id = int(match.group(2))
                
                if image_types is None or image_type in image_types:
                    if image_type not in latest_images or image_id > latest_images[image_type]['image_id']:
                        latest_images[image_type] = {
                            'filename': image_file,
                            'image_id': image_id
                        }
            else:
                # For images without image_id, just include them
                base_name = filename.replace('.png', '').replace('.jpg', '').replace('.jpeg', '')
                if image_types is None or base_name in image_types:
                    latest_images[base_name] = {
                        'filename': image_file,
                        'image_id': 0
                    }
        
        return {
            'success': True,
            'project_id': project_id,
            'latest_images': {k: v['filename'] for k, v in latest_images.items()},
            'image_details': latest_images,
            'total_latest_images': len(latest_images),
            'message': f"Found {len(latest_images)} latest images for project {project_id}"
        }
        
    except Exception as e:
        logger.error(f"Error getting latest images: {e}")
        return {
            'success': False,
            'error': f"Failed to get latest images: {str(e)}"
        }

@tool
def analyze_simulation_results(project_id: str) -> Dict[str, Any]:
    """
    Analyze simulation results to determine if layout optimization is needed.
    
    Args:
        project_id (str): unique project identifier
        
    Returns:
        Dict containing simulation analysis and optimization recommendations
    """
    logger.info(f"Analyzing simulation results for project: {project_id}")
    
    try:
        # This would typically load simulation results from cache or files
        # For now, return a template structure
        
        analysis = {
            'capacity_factor': None,
            'wake_losses': None,
            'aep_gwh': None,
            'num_turbines': None,
            'mean_wind_speed': None,
            'performance_rating': 'unknown',
            'optimization_needed': False,
            'recommendations': [],
            'has_simulation_data': False
        }
        
        # Try to extract metrics from simulation cache
        try:
            from .simulation_tools import SIMULATION_CACHE
            
            # Find latest simulation for this project by timestamp
            latest_sim = None
            latest_timestamp = None
            
            for sim_id, sim_data in SIMULATION_CACHE.items():
                if sim_data.get('project_id') == project_id:
                    sim_timestamp = sim_data.get('timestamp')
                    logger.info(f"Found simulation {sim_id} with timestamp {sim_timestamp}")
                    if sim_timestamp and (latest_timestamp is None or sim_timestamp > latest_timestamp):
                        latest_sim = sim_data
                        latest_timestamp = sim_timestamp
                        logger.info(f"Latest simulation updated to {sim_id} with timestamp {latest_timestamp}")
            
            if latest_sim:
                if 'capacity_factor' in latest_sim:
                    analysis['capacity_factor'] = latest_sim['capacity_factor']
                if 'wake_loss_percent' in latest_sim:
                    analysis['wake_losses'] = latest_sim['wake_loss_percent']
                if 'total_aep_gwh' in latest_sim:
                    analysis['aep_gwh'] = latest_sim['total_aep_gwh']
                if 'number_of_turbines' in latest_sim:
                    analysis['num_turbines'] = latest_sim['number_of_turbines']
                if 'mean_wind_speed' in latest_sim:
                    analysis['mean_wind_speed'] = latest_sim['mean_wind_speed']
                analysis['has_simulation_data'] = True
                analysis['simulation_timestamp'] = latest_timestamp
                logger.info(f"Simulation metrics extracted: {analysis}")
        except Exception as e:
            logger.warning(f"Could not access simulation cache: {e}")
        
        # Analyze performance with detailed recommendations
        if analysis['capacity_factor'] is not None:
            cf = analysis['capacity_factor']*100
            if cf > 40:
                analysis['performance_rating'] = 'excellent'
                analysis['recommendations'].append(f"Excellent capacity factor ({cf:.1f}%) - layout is well optimized")
            elif cf > 35:
                analysis['performance_rating'] = 'good'
                analysis['recommendations'].append(f"Good capacity factor ({cf:.1f}%) - minor optimizations possible")
            elif cf > 30:
                analysis['performance_rating'] = 'acceptable'
                analysis['recommendations'].append(f"Acceptable capacity factor ({cf:.1f}%) - consider layout improvements")
                analysis['optimization_needed'] = True
            else:
                analysis['performance_rating'] = 'poor'
                analysis['optimization_needed'] = True
                analysis['recommendations'].append(f"Poor capacity factor ({cf:.1f}%) - layout optimization strongly recommended")
                analysis['recommendations'].append("Consider: alternative sites, different layout algorithm, or increased spacing")
        
        if analysis['wake_losses'] is not None:
            wl = analysis['wake_losses']
            if wl > 15:
                analysis['optimization_needed'] = True
                analysis['recommendations'].append(f"High wake losses ({wl:.1f}%) - increase turbine spacing or try offset grid layout")
            elif wl > 10:
                analysis['recommendations'].append(f"Moderate wake losses ({wl:.1f}%) - spacing optimization could improve performance")
            else:
                analysis['recommendations'].append(f"Low wake losses ({wl:.1f}%) - good turbine spacing")
        
        # Add summary message
        if not analysis['has_simulation_data']:
            analysis['recommendations'].append("No simulation data found - run simulation first")

        logger.info(f"Final analyze simulation results metrics: {analysis}")

        return {
            'success': True,
            'project_id': project_id,
            'analysis': analysis,
            'message': f"Simulation analysis complete - Performance: {analysis['performance_rating']}",
            'optimization_needed': analysis['optimization_needed']
        }
        
    except Exception as e:
        logger.error(f"Error analyzing simulation results: {e}")
        return {
            'success': False,
            'error': f"Failed to analyze simulation: {str(e)}"
        }