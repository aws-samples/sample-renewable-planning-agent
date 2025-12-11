import pandas as pd
import logging
from PIL import Image
import math
import io
import tempfile
import matplotlib.pyplot as plt
from strands import tool
import requests
import json
import os
import folium
from shapely.geometry import shape, Point
from shapely.ops import unary_union
import geopandas as gpd
import numpy as np
from .storage_utils import save_file_with_storage

import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend

logger = logging.getLogger(__name__)


def add_feature_types_fallback(geojson_data):
    """Add feature_type to properties when simplification fails"""
    for feature in geojson_data.get('features', []):
        props = feature.get('properties', {})
        if 'feature_type' not in props:
            # Determine feature type based on properties
            if props.get('building'):
                props['feature_type'] = 'buildings'
            elif props.get('highway'):
                props['feature_type'] = 'roads'
            elif props.get('natural') == 'water' or props.get('waterway'):
                props['feature_type'] = 'water'
            else:
                props['feature_type'] = 'other'
    return geojson_data


def query_overpass(lat, lon, radius_km=5, residence_setback_m=300, road_setback_m=110, lines_setback_m=110, water_setback_m=30.48, default_setback_m=100):
    """Query Overpass API for terrain features around a location with adjustable setback"""

    logger.info(
        f"Starting Overpass query for lat={lat}, lon={lon}, radius={radius_km}km")

    # Convert radius to degrees (approximate)
    radius_deg = radius_km / 111.32

    # Calculate bounding box
    south = lat - radius_deg
    north = lat + radius_deg
    west = lon - radius_deg
    east = lon + radius_deg

    # Overpass query with geometry output
    query = f"""
    [out:json][timeout:25];
    (
      // Water Bodies
      way["natural"="water"]({south},{west},{north},{east});
      relation["natural"="water"]({south},{west},{north},{east});
      way["waterway"="river"]({south},{west},{north},{east});
      way["waterway"="stream"]({south},{west},{north},{east});
      way["waterway"="canal"]({south},{west},{north},{east});
      way["water"="lake"]({south},{west},{north},{east});
      way["water"="pond"]({south},{west},{north},{east});
      way["water"="reservoir"]({south},{west},{north},{east});
      way["natural"="wetland"]({south},{west},{north},{east});
      way["natural"="coastline"]({south},{west},{north},{east});
      node["natural"="spring"]({south},{west},{north},{east});
      node["natural"="hot_spring"]({south},{west},{north},{east});
      node["waterway"="waterfall"]({south},{west},{north},{east});

      // Buildings and Structures
      way["building"]({south},{west},{north},{east});
      relation["building"]({south},{west},{north},{east});
      way["man_made"]({south},{west},{north},{east});
      node["man_made"]({south},{west},{north},{east});
      way["building"="residential"]({south},{west},{north},{east});
      way["building"="commercial"]({south},{west},{north},{east});
      way["building"="industrial"]({south},{west},{north},{east});
      way["building"="retail"]({south},{west},{north},{east});
      way["building"="warehouse"]({south},{west},{north},{east});
      way["building"="church"]({south},{west},{north},{east});
      way["building"="mosque"]({south},{west},{north},{east});
      way["building"="temple"]({south},{west},{north},{east});
      way["building"="school"]({south},{west},{north},{east});
      way["building"="hospital"]({south},{west},{north},{east});

      // Infrastructure
      way["highway"]({south},{west},{north},{east});
      way["railway"]({south},{west},{north},{east});
      way["bridge"]({south},{west},{north},{east});
      way["tunnel"]({south},{west},{north},{east});

      // Other structures
      way["leisure"]({south},{west},{north},{east});
      way["amenity"]({south},{west},{north},{east});
      node["amenity"]({south},{west},{north},{east});
      way["landuse"="industrial"]({south},{west},{north},{east});
      way["landuse"="commercial"]({south},{west},{north},{east});
    );
    out geom;
    """

    # Make request to Overpass API
    url = os.getenv('OVERPASS_API_URL')

    response = requests.post(url, data=query, timeout=30)
    logger.info(f"Overpass API response status: {response.status_code}")

    if response.status_code != 200:
        logger.error(
            f"Overpass API error: {response.status_code}, response: {response.text[:500]}")
        return {"type": "FeatureCollection", "features": []}

    # Convert to GeoJSON
    osm_data = response.json()
    logger.info(
        f"OSM data contains {len(osm_data.get('elements', []))} elements")

    geojson_data = osm_to_geojson(osm_data)
    logger.info(
        f"Converted to GeoJSON with {len(geojson_data.get('features', []))} features")

    # Filter features within radius
    geojson_data = filter_by_radius(geojson_data, lat, lon, radius_km)
    logger.info(
        f"After radius filter: {len(geojson_data.get('features', []))} features")

    # Apply setback with different distances based on feature type
    geojson_data = apply_setback(geojson_data, residence_setback_m,
                                 road_setback_m, lines_setback_m, water_setback_m, default_setback_m)
    logger.info(
        f"After setback: {len(geojson_data.get('features', []))} features")

    # Simplify by merging geometries
    geojson_data = simplify_geojson_union(geojson_data)
    logger.info(
        f"After simplification: {len(geojson_data.get('features', []))} features")

    return geojson_data


def filter_by_radius(geojson_data, center_lat, center_lon, radius_km):
    """Filter features to only include those within radius of center point"""

    gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
    if gdf.empty:
        return geojson_data

    # Create center point
    center_point = Point(center_lon, center_lat)

    # Set CRS and convert to UTM for accurate distance
    gdf.crs = 'EPSG:4326'
    gdf_utm = gdf.to_crs('EPSG:32614')
    center_utm = gpd.GeoSeries(
        [center_point], crs='EPSG:4326').to_crs('EPSG:32614').iloc[0]

    # Filter by distance
    radius_m = radius_km * 1000
    gdf_filtered = gdf_utm[gdf_utm.distance(center_utm) <= radius_m]

    # Convert back to WGS84
    gdf_filtered = gdf_filtered.to_crs('EPSG:4326')

    return json.loads(gdf_filtered.to_json())


def osm_to_geojson(osm_data):
    """Convert OSM data to GeoJSON format"""

    features = []

    for element in osm_data['elements']:
        if element['type'] == 'way' and 'geometry' in element:
            coords = [[pt['lon'], pt['lat']] for pt in element['geometry']]

            if len(coords) > 1:
                geom_type = "Polygon" if coords[0] == coords[-1] and len(
                    coords) > 3 else "LineString"
                if geom_type == "Polygon":
                    coords = [coords]

                features.append({
                    "type": "Feature",
                    "geometry": {"type": geom_type, "coordinates": coords},
                    "properties": element.get('tags', {})
                })

    return {"type": "FeatureCollection", "features": features}


def apply_setback(geojson_data, residence_setback_m=300, road_setback_m=110, lines_setback_m=110, water_setback_m=30.48, default_setback_m=100):
    """Apply setback buffer to non-buildable features based on obstacle type"""

    # Convert to GeoDataFrame for easier processing
    gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])

    if gdf.empty:
        return geojson_data

    # Set CRS to WGS84
    gdf.crs = 'EPSG:4326'

    # Convert to UTM for accurate distance calculations
    # Use UTM zone 14N for Texas (approximate)
    gdf_utm = gdf.to_crs('EPSG:32614')

    # Apply different setbacks based on feature type
    setback_info = []
    for idx, row in gdf_utm.iterrows():
        # Get properties from the original columns (excluding geometry)
        props = {}
        for col in gdf_utm.columns:
            if col != 'geometry':
                props[col] = row[col] if pd.notna(row[col]) else ''

        # Determine setback based on feature type
        if is_residence_receptor(props):
            buffer_distance = residence_setback_m
            feature_type = 'residence'
        elif is_road_railroad_transmission(props):
            buffer_distance = road_setback_m
            feature_type = 'infrastructure'
        elif is_pipeline_distribution(props):
            buffer_distance = lines_setback_m
            feature_type = 'pipeline'
        elif is_water_wetland(props):
            buffer_distance = water_setback_m
            feature_type = 'water'
        else:
            # Default setback for other features
            buffer_distance = default_setback_m or 100
            feature_type = 'other'

        # Apply buffer
        gdf_utm.at[idx, 'geometry'] = row.geometry.buffer(buffer_distance)

        # Store setback info
        setback_info.append({
            'setback_applied': True,
            'default_setback_m': buffer_distance,
            'setback_type': feature_type
        })

    # Convert back to WGS84
    gdf_buffered = gdf_utm.to_crs('EPSG:4326')

    # Add setback information to the GeoDataFrame
    for idx, info in enumerate(setback_info):
        for key, value in info.items():
            gdf_buffered.at[gdf_buffered.index[idx], key] = value

    # Convert back to GeoJSON
    return json.loads(gdf_buffered.to_json())


def is_residence_receptor(props):
    """Check if feature is a residence or receptor"""
    building_type = props.get('building', '')
    amenity = props.get('amenity', '')
    landuse = props.get('landuse', '')

    return (building_type in ['residential', 'house', 'apartments', 'detached', 'terrace'] or
            amenity in ['school', 'hospital', 'clinic', 'nursing_home', 'kindergarten'] or
            landuse == 'residential')


def is_road_railroad_transmission(props):
    """Check if feature is road, railroad, transmission line, or existing structure"""
    highway = props.get('highway', '')
    railway = props.get('railway', '')
    power = props.get('power', '')
    man_made = props.get('man_made', '')
    building = props.get('building', '')

    return (highway or railway or
            power in ['line', 'tower', 'pole', 'substation'] or
            man_made in ['tower', 'mast', 'antenna'] or
            building in ['commercial', 'industrial', 'retail', 'warehouse', 'church', 'mosque', 'temple'])


def is_pipeline_distribution(props):
    """Check if feature is pipeline or distribution line"""
    man_made = props.get('man_made', '')
    power = props.get('power', '')

    return (man_made in ['pipeline', 'petroleum_well', 'gas_well'] or
            power in ['minor_line', 'cable'])


def is_water_wetland(props):
    """Check if feature is water body, stream, or wetland"""
    natural = props.get('natural', '')
    waterway = props.get('waterway', '')
    water = props.get('water', '')

    return (natural in ['water', 'wetland', 'coastline'] or
            waterway in ['river', 'stream', 'canal'] or
            water in ['lake', 'pond', 'reservoir'])


def simplify_geojson_union(geojson_data):
    """Reduce GeoJSON size by merging overlapping/adjacent polygons by type"""

    try:
        gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
        if gdf.empty:
            return geojson_data

        # Medium simplification (tolerance ~30m) + remove small areas
        gdf['geometry'] = gdf.geometry.simplify(
            tolerance=0.0003, preserve_topology=True)

        # Remove tiny polygons (less than ~500 sq meters)
        gdf = gdf[gdf.geometry.area > 0.000001]

        # Group by feature type with safe column access
        building_mask = gdf['building'].notna() if 'building' in gdf.columns else pd.Series([
            False] * len(gdf), index=gdf.index)
        highway_mask = gdf['highway'].notna() if 'highway' in gdf.columns else pd.Series([
            False] * len(gdf), index=gdf.index)
        natural_water_mask = (gdf['natural'] == 'water') if 'natural' in gdf.columns else pd.Series(
            [False] * len(gdf), index=gdf.index)
        waterway_mask = gdf['waterway'].notna() if 'waterway' in gdf.columns else pd.Series([
            False] * len(gdf), index=gdf.index)

        groups = {
            'buildings': gdf[building_mask],
            'roads': gdf[highway_mask],
            'water': gdf[natural_water_mask | waterway_mask],
            'other': gdf[~building_mask & ~highway_mask & ~natural_water_mask & ~waterway_mask]
        }

        merged_features = []
        for group_name, group_gdf in groups.items():
            if not group_gdf.empty:
                merged_geom = unary_union(group_gdf.geometry)
                # Post-union simplification
                merged_geom = merged_geom.simplify(
                    tolerance=0.0003, preserve_topology=True)
                merged_features.append({
                    "type": "Feature",
                    "geometry": merged_geom.__geo_interface__,
                    "properties": {
                        "feature_type": group_name,
                        "original_count": len(group_gdf)
                    }
                })

        return {"type": "FeatureCollection", "features": merged_features}
    except Exception as e:
        logger.error(f"Simplification failed: {e}")
        # Return original data with feature_type added to each feature
        return add_feature_types_fallback(geojson_data)


def save_analysis_results(geojson_data, latitude, longitude, project_id):
    """Save GeoJSON data and create interactive map"""

    try:
        # Define filenames without project_id
        geojson_filename = "boundaries.geojson"
        map_filename = "boundaries.html"
        png_filename = "boundaries.png"

        # Save GeoJSON using storage utility
        save_file_with_storage(
            json.dumps(geojson_data, indent=2),
            project_id,
            geojson_filename,
            "text",
            "terrain_agent"
        )

        # Create interactive map with ArcGIS World Imagery basemap
        m = folium.Map(location=[latitude, longitude], zoom_start=12)

        # Add USGS Imagery basemap
        folium.TileLayer(
            tiles='https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer/tile/{z}/{y}/{x}',
            attr='USGS',
            name='USGS Imagery',
            overlay=False,
            control=True
        ).add_to(m)

        # Add features with different colors based on type
        for feature in geojson_data.get('features', []):
            feature_type = feature.get('properties', {}).get(
                'feature_type', 'other')

            if feature_type == 'water':
                color_style = {'fillColor': 'blue', 'color': 'darkblue',
                               'weight': 2, 'fillOpacity': 0.4, 'opacity': 0.8}
            elif feature_type == 'roads':
                color_style = {'fillColor': 'orange', 'color': 'darkorange',
                               'weight': 2, 'fillOpacity': 0.4, 'opacity': 0.8}
            elif feature_type == 'buildings':
                color_style = {'fillColor': 'red', 'color': 'darkred',
                               'weight': 2, 'fillOpacity': 0.4, 'opacity': 0.8}
            else:
                color_style = {'fillColor': 'purple', 'color': 'darkviolet',
                               'weight': 2, 'fillOpacity': 0.4, 'opacity': 0.8}

            folium.GeoJson(feature, style_function=lambda x,
                           style=color_style: style).add_to(m)

        # Add center marker
        folium.Marker([latitude, longitude], popup="Analysis Center").add_to(m)

        # Save HTML map to temp file and use storage utility
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as temp_file:
            m.save(temp_file.name)
            save_file_with_storage(
                temp_file.name,
                project_id,
                map_filename,
                "file_copy",
                "terrain_agent"
            )
            temp_file.flush()
            temp_file.close()

        # Create and save PNG image using satellite imagery
        try:
            # Calculate bounding box
            radius_m = 5000
            meters_per_degree = 111319.9
            radius_deg_lat = radius_m / meters_per_degree
            radius_deg_lon = radius_m / \
                (meters_per_degree * abs(math.cos(math.radians(latitude))))

            bbox_west = longitude - radius_deg_lon
            bbox_east = longitude + radius_deg_lon
            bbox_south = latitude - radius_deg_lat
            bbox_north = latitude + radius_deg_lat

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

            response = requests.get(service_url, params=params, timeout=60)

            logger.info(
                f"Requesting satellite imagery from USGS: {response.status_code}")
            if response.status_code == 200:
                base_image = Image.open(io.BytesIO(response.content))
                if base_image.mode in ('RGBA', 'LA'):
                    base_image = base_image.convert('RGB')

                # Convert bbox to Web Mercator for proper alignment
                from pyproj import Transformer
                transformer = Transformer.from_crs(
                    'EPSG:4326', 'EPSG:3857', always_xy=True)
                west_3857, south_3857 = transformer.transform(
                    bbox_west, bbox_south)
                east_3857, north_3857 = transformer.transform(
                    bbox_east, bbox_north)

                # Create figure
                fig, ax = plt.subplots(figsize=(12, 8))
                extent_3857 = [west_3857, east_3857, south_3857, north_3857]
                ax.imshow(base_image, extent=extent_3857, aspect='equal')

                # Convert and plot features in Web Mercator
                gdf_plot = gpd.GeoDataFrame.from_features(
                    geojson_data['features'])
                if not gdf_plot.empty:
                    gdf_plot.crs = 'EPSG:4326'
                    gdf_plot = gdf_plot.to_crs('EPSG:3857')

                    if 'feature_type' in gdf_plot.columns:
                        for feature_type in gdf_plot['feature_type'].unique():
                            subset = gdf_plot[gdf_plot['feature_type']
                                              == feature_type]
                            if feature_type == 'water':
                                subset.plot(ax=ax, color='blue', alpha=0.6,
                                            edgecolor='darkblue', linewidth=1)
                            elif feature_type == 'roads':
                                subset.plot(
                                    ax=ax, color='orange', alpha=0.6, edgecolor='darkorange', linewidth=1)
                            elif feature_type == 'buildings':
                                subset.plot(ax=ax, color='red', alpha=0.6,
                                            edgecolor='darkred', linewidth=1)
                            else:
                                subset.plot(
                                    ax=ax, color='purple', alpha=0.6, edgecolor='darkviolet', linewidth=1)
                    else:
                        gdf_plot.plot(ax=ax, color='purple', alpha=0.6,
                                      edgecolor='darkviolet', linewidth=1)

                ax.set_title(
                    f'Unbuildable Areas - {latitude:.4f}, {longitude:.4f}', fontsize=12)
                ax.set_xlabel('Longitude')
                ax.set_ylabel('Latitude')
                ax.set_xlim(extent_3857[0], extent_3857[1])
                ax.set_ylim(extent_3857[2], extent_3857[3])
                ax.set_aspect('equal')

                # Format axis labels to show lat/lon instead of Web Mercator meters
                ax.tick_params(axis='both', which='major', labelsize=8)

                def format_lon(x, p):
                    lon, _ = transformer.transform(
                        x, extent_3857[2], direction='INVERSE')
                    return f'{lon:.3f}'

                def format_lat(y, p):
                    _, lat = transformer.transform(
                        extent_3857[0], y, direction='INVERSE')
                    return f'{lat:.3f}'

                ax.xaxis.set_major_formatter(plt.FuncFormatter(format_lon))
                ax.yaxis.set_major_formatter(plt.FuncFormatter(format_lat))

                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    plt.savefig(temp_file.name, dpi=250,
                                bbox_inches='tight', facecolor='white')
                    plt.close()

                    save_file_with_storage(
                        temp_file.name,
                        project_id,
                        png_filename,
                        "file_copy",
                        "terrain_agent"
                    )
                    temp_file.flush()
                    temp_file.close()
            else:
                logger.warning(
                    f"Failed to get satellite imagery: HTTP {response.status_code}")
                logger.info(f"Response content: {response.text[:200]}")

        except Exception as e:
            logger.error(f"PNG export failed: {e}", exc_info=True)

        return {
            "geojson_filename": geojson_filename,
            "map_filename": map_filename,
            "png_filename": png_filename,
            "message": "Files saved successfully"
        }

    except Exception as e:
        logger.error(f"Failed to save results: {str(e)}", exc_info=True)
        return {"error": f"Failed to save results: {str(e)}"}


@tool
def get_unbuildable_areas(latitude: float, longitude: float, project_id: str,
                          radius_km: float, default_setback_m: int,
                          tip_height_m: float, rotor_radius_m: float,
                          residence_setback_m: float, road_setback_m: float,
                          water_setback_m: float, lines_setback_m: float) -> dict:
    """
    Analyze terrain and identify unbuildable areas (exclusion zones) for renewable energy projects.

    This tool queries geographic databases to find terrain features that create constraints for 
    wind and solar installations, including water bodies, buildings, roads, and other infrastructure.
    If verious setbacks are not provided, the following setbacks are applied (in meters):
    - Residences/Receptors: 3 × Tip Height
    - Roads/Railroads/Transmission Lines/Existing Structures: 1.1 × Tip Height  
    - Pipelines/Distribution Lines: 1.1 × Rotor Radius
    - Streams/Wetlands/Waterbodies: 100 feet (30.48m)
    If no setbacks and no turbine details are provided, it uses the default_setback.

    Results are automatically saved to the assets folder as both GeoJSON and interactive map.

    Args:
        latitude (float): Latitude coordinate for the analysis center point (required)
        longitude (float): Longitude coordinate for the analysis center point (required)
        project_id (str): unique project identifier (required)
        radius_km (float): Analysis radius in kilometers (default: 5.0, max recommended: 10.0)
        default_setback_m (int): Default setback distance in meters for features without specific rules (default: 100)
        tip_height_m (float): Turbine tip height in meters for calculating setbacks 
        rotor_radius_m (float): Turbine rotor radius in meters for calculating setbacks
        residence_setback_m (float): Setback from residences/receptors in meters
        roads_setback_m (float): Setback from roads/railroads/transmission lines/existing structures in meters
        lines_setback_m (float): Setback from pipelines or distribution lines in meters
        water_setback_m (float): Setback from streams/wetlands/waterbodies in meters

    Returns:
        dict: Analysis results containing:
            - success (bool): Whether analysis completed successfully
            - GeoJSON_data (dict): Boundary data for unbuildable areas
            - project_id (str): The project identifier used for saved files
            - saved_files (dict): Paths to saved GeoJSON and map files
            - message (str): Status message with file information
            - error (str): Error details if analysis failed

    Note: Files are saved as '<project_id>_boundaries.geojson' and '<project_id>_map.html'
    Map colors: Blue=Water, Orange=Roads, Red=Buildings, Purple=Other
    """

    try:
        logger.info(
            f"Starting terrain analysis for coordinates {latitude}, {longitude}")
        logger.info(
            f"Parameters: radius_km={radius_km}, default_setback_m={default_setback_m}, project_id={project_id}")
        logger.info(
            f"Turbine specs: tip_height_m={tip_height_m}, rotor_radius_m={rotor_radius_m}")
        logger.info(
            f"Setbacks in prompt: residence={residence_setback_m}, roads={road_setback_m}, lines={lines_setback_m}, water={water_setback_m}")

        if residence_setback_m is None:
            # Residence/Receptors = 1.1 × Rotor Radius
            residence_setback_m = 3 * tip_height_m if tip_height_m else default_setback_m or 300
        if road_setback_m is None:
            # Roads/Railroads, Transmission Lines, Existing Structures = 1.1 × Tip Height
            road_setback_m = 1.1 * tip_height_m if tip_height_m else default_setback_m or 110
        if lines_setback_m is None:
            # Pipelines/Distribution Lines = 1.1 × Rotor Radius
            lines_setback_m = 1.1 * rotor_radius_m if rotor_radius_m else default_setback_m or 110
        if water_setback_m is None:
            # Streams/Wetlands/Waterbodies = 100 feet (30.48 meters)
            water_setback_m = 30.48

        # Query terrain features with setback
        terrain_data = query_overpass(latitude, longitude, radius_km, residence_setback_m,
                                      road_setback_m, lines_setback_m, water_setback_m, default_setback_m)
        logger.info(
            f"Overpass query completed. Found {len(terrain_data.get('features', []))} features")

        # Save results to assets folder
        save_result = save_analysis_results(
            terrain_data, latitude, longitude, project_id)

        if "error" in save_result:
            logger.error(f"Save failed: {save_result['error']}")
            return {
                "success": False,
                "error": save_result["error"]
            }

        return {
            "success": True,
            "GeoJSON_data": terrain_data,
            "project_id": project_id,
            "saved_files": save_result,
            "message": f"Analysis completed with constraint-based setbacks. Files saved with ID: {project_id}"
        }

    except Exception as e:
        logger.error(f"Terrain analysis failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": f"Analysis failed: {str(e)}"
        }
