from .shared_tools import get_turbine_specs
from .storage_utils import load_file_from_storage, save_file_with_storage
from strands.tools import tool
import matplotlib.pyplot as plt
import matplotlib
from turbine_models.parser import Turbines
from py_wake.site import UniformWeibullSite
from ast import literal_eval
from py_wake.wind_turbines.power_ct_functions import PowerCtTabular
from py_wake.wind_turbines import WindTurbine
from py_wake.examples.data.iea37._iea37 import IEA37_WindTurbines
from py_wake import IEA37SimpleBastankhahGaussian
import numpy as np
import os
import warnings
from datetime import datetime
from scipy import stats
import hashlib
from typing import Dict, Optional, Any
import json
import io
import tempfile
import pandas as pd

# Configure logging
import logging

logger = logging.getLogger(__name__)

# Suppress specific PyWake warnings
warnings.filterwarnings(
    "ignore", message="The IEA37SimpleBastankhahGaussian model is not representative")

# Import PyWake components after suppressing warnings

# Set matplotlib to use non-interactive backend to avoid thread issues
matplotlib.use('Agg')  # Must be before importing pyplot


# Global cache for complex objects needed for report generation
SIMULATION_CACHE = {}


def create_simplified_wind_conditions(wind_conditions, top_n=5):
    """Create simplified wind conditions using top N sectors by probability"""
    logger.info(
        f"Creating simplified wind conditions with top {top_n} sectors")

    try:
        # Convert to numpy arrays if needed
        p_wd = np.array(wind_conditions['p_wd'])
        wd_bins = np.array(wind_conditions['wd_bins'])
        a = np.array(wind_conditions['a'])
        k = np.array(wind_conditions['k'])
        logger.info(f"Wind conditions loaded: {len(p_wd)} sectors found")

        # Get indices of top N sectors by probability
        top_indices = np.argsort(p_wd)[-top_n:]
        logger.info(f"Selected top {len(top_indices)} sectors by probability")

        # Extract top sectors
        simplified_conditions = {
            'wd_sectors': wd_bins[top_indices].tolist(),
            'p_wd': p_wd[top_indices].tolist(),
            'a': a[top_indices].tolist(),
            'k': k[top_indices].tolist(),
            'ti': wind_conditions['ti']
        }

        # Renormalize probabilities
        total_prob = sum(simplified_conditions['p_wd'])
        simplified_conditions['p_wd'] = [
            p/total_prob for p in simplified_conditions['p_wd']]

        logger.info(
            f"Simplified wind conditions created successfully with {len(simplified_conditions['p_wd'])} sectors")
        return simplified_conditions

    except KeyError as e:
        logger.error(f"Missing key in wind conditions: {str(e)}")
        raise ValueError(
            f"Missing required wind condition parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating simplified wind conditions: {str(e)}")
        raise


def create_wind_turbine(turbine_model: str) -> WindTurbine:
    """Create a WindTurbine object from turbine specifications."""
    logger.info(f"Creating wind turbine: {turbine_model}")
    turbine = IEA37_WindTurbines()
    try:
        if turbine_model is not None:
            # Get turbine specs with fuzzy matching
            logger.info(f"Getting specs for turbine: {turbine_model}")
            turbine_specs = get_turbine_specs(turbine_model)
            logger.info(
                f"Turbine specs retrieved: {turbine_specs is not None}")
            if turbine_specs:
                # Create the Power Curve Object from DataFrame
                logger.info("Creating custom turbine from specs")
                power_curve_df = turbine_specs['power_curve']
                power_ct_function = PowerCtTabular(
                    power_curve_df['wind_speed_ms'].values,
                    power_curve_df['power_kw'].values,
                    'kW',
                    power_curve_df['ct'].values,
                    method='linear',
                    ws_cutin=turbine_specs['cut_in_wind_speed'],
                    ws_cutout=turbine_specs['cut_out_wind_speed']
                )
                # Create the turbine
                turbine = WindTurbine(
                    name=turbine_specs["name"],
                    diameter=turbine_specs['rotor_diameter'],
                    hub_height=turbine_specs["hub_height"],
                    powerCtFunction=power_ct_function
                )
                logger.info(
                    f"Turbine created successfully: {turbine_specs['name']}")
            else:
                logger.info("Using IEA37 Wind Turbine")
        else:
            logger.info("Turbine model not defined, using IEA37 Wind Turbine")

    except Exception as e:
        logger.error(f"Error in turbine creation: {str(e)}")
        logger.error("Using IEA37 Wind Turbine")

    return turbine


def load_turbine_layout_geojson(project_id: str) -> Dict[str, Any]:
    """
    Load turbine layout GeoJSON using the unique ID from terrain analysis.

    Args:
        project_id: unique identifier from terrain analysis

    Returns:
        Dict containing GeoJSON data or raises exception if not found
    """
    try:
        filename = "turbine_layout.geojson"
        file_path = load_file_from_storage(
            project_id, filename, "layout_agent")

        with open(file_path, 'r') as file:
            geojson_data = json.load(file)

        logger.info(f"Loaded turbine layout from {project_id}/{filename}")
        return geojson_data

    except FileNotFoundError:
        logger.error(f"Turbine layout file not found: {project_id}/{filename}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Invalid GeoJSON file: {project_id}/{filename}")
        return None
    except Exception as e:
        logger.error(f"Error loading turbine layout: {str(e)}")
        return None


def run_simplified_flow_map_simulation(simplified_conditions, turbines_geojson, turbine_model=None):
    """Run fast flow map simulation with simplified wind conditions"""
    logger.info("Running simplified flow map simulation")

    try:
        # Extract turbine positions
        turbine_positions = []
        center_lon = np.mean([f['geometry']['coordinates'][0]
                             for f in turbines_geojson['features']])
        center_lat = np.mean([f['geometry']['coordinates'][1]
                             for f in turbines_geojson['features']])
        logger.info(f"Center coordinates: lon={center_lon}, lat={center_lat}")
        logger.info(
            f"Processing {len(turbines_geojson['features'])} turbines for flow map")

        for feature in turbines_geojson['features']:
            coords = feature['geometry']['coordinates']
            x = (coords[0] - center_lon) * 111000 * \
                np.cos(np.radians(center_lat))
            y = (coords[1] - center_lat) * 111000
            turbine_positions.append([x, y])

        logger.info(
            f"Converted {len(turbine_positions)} turbine positions to local coordinates")

        # Create turbine and site with proper data types
        turbine = create_wind_turbine(turbine_model)

        site = UniformWeibullSite(
            p_wd=np.array(simplified_conditions['p_wd'], dtype=float),
            a=np.array(simplified_conditions['a'], dtype=float),
            k=np.array(simplified_conditions['k'], dtype=float),
            ti=float(simplified_conditions['ti'])
        )

        # Initialize wake model
        logger.info("Initializing wake model")
        wake_model = IEA37SimpleBastankhahGaussian(site, turbine)
        positions = np.array(turbine_positions)
        x_positions = positions[:, 0]
        y_positions = positions[:, 1]

        # Run simulation with specific wind directions
        logger.info("Running flow map simulation")
        sim_result = wake_model(x_positions, y_positions,
                                wd=np.array(
                                    simplified_conditions['wd_sectors'], dtype=float),
                                TI=float(simplified_conditions['ti']))

        logger.info("Generating flow map")
        flow_map = sim_result.flow_map()
        logger.info("Flow map simulation completed successfully")

        return flow_map, sim_result

    except Exception as e:
        logger.warning(f"Error in flow map simulation: {str(e)}")
        raise


@tool
def run_wake_simulation(wind_conditions: Dict, project_id: str, calculate_flow_map: bool = True, turbine_model: Optional[str] = None) -> Dict:
    """
    Run wake simulation using processed wind conditions and turbine layout

    Args:
        wind_conditions: Dict of processed wind conditions. Example: 
        {
            'p_wd': [0.1, 0.9],
            'a': [8.0, 9.0],
            'k': [2.0, 2.0],
            'wd_bins': [0, 90, 180, 270, 360],
            'ti': 0.1,
            'mean_wind_speed': 8.4,
            'total_hours': 8760
        }
        project_id: unique identifier from terrain analysis to load turbine layout
        calculate_flow_map: Whether to calculate flow map (default: True)
        turbine_model: Model of the turbine used

    Returns:
        Dict containing simulation results
    """
    logger.info(
        f"Starting wake simulation. project_id: {project_id}, calculate_flow_map: {calculate_flow_map}, turbine_model: {turbine_model}")

    try:
        # Load turbine layout from file
        logger.info(f"Loading turbine layout for project_id: {project_id}")
        turbines_geojson = load_turbine_layout_geojson(project_id)

        # Extract turbine positions and convert to local coordinates
        logger.info("Processing turbine layout")
        turbine_positions = []
        center_lon = np.mean([f['geometry']['coordinates'][0]
                             for f in turbines_geojson['features']])
        center_lat = np.mean([f['geometry']['coordinates'][1]
                             for f in turbines_geojson['features']])
        logger.info(
            f"Processing {len(turbines_geojson['features'])} turbines at center coordinates: lon={center_lon:.4f}, lat={center_lat:.4f}")

        for feature in turbines_geojson['features']:
            coords = feature['geometry']['coordinates']
            # Convert lat/lon to local UTM-like coordinates (meters)
            x = (coords[0] - center_lon) * 111000 * \
                np.cos(np.radians(center_lat))
            y = (coords[1] - center_lat) * 111000
            turbine_positions.append([x, y])

        logger.info(
            f"Converted {len(turbine_positions)} turbine positions to local coordinates")

        turbine = create_wind_turbine(turbine_model)

        # Ensure wind conditions are in the correct format
        logger.info("Processing wind conditions")
        p_wd = np.array(wind_conditions['p_wd'], dtype=float)
        a = np.array(wind_conditions['a'], dtype=float)
        k = np.array(wind_conditions['k'], dtype=float)
        ti = float(wind_conditions['ti'])
        logger.info(
            f"Wind conditions: {len(p_wd)} sectors, mean a={np.mean(a):.2f}, mean k={np.mean(k):.2f}, ti={ti:.2f}")

        # Create site with Weibull wind conditions
        logger.info("Creating Weibull site model")
        site = UniformWeibullSite(
            p_wd=p_wd,
            a=a,
            k=k,
            ti=ti
        )
    except KeyError as e:
        error_msg = f"Missing key in input parameters: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = f"Error setting up simulation parameters: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

    try:
        # Initialize wake model using IEA37SimpleBastankhahGaussian
        logger.info("Initializing wake model (IEA37SimpleBastankhahGaussian)")
        wake_model = IEA37SimpleBastankhahGaussian(site, turbine)

        # Convert positions to numpy array
        positions = np.array(turbine_positions)
        x_positions = positions[:, 0]
        y_positions = positions[:, 1]
        logger.info(
            f"Position arrays created: x_range=[{min(x_positions):.1f}, {max(x_positions):.1f}], y_range=[{min(y_positions):.1f}, {max(y_positions):.1f}]")

        # Run simulation
        logger.info("Running wake simulation")
        sim_result = wake_model(x_positions, y_positions)
        logger.info("Wake simulation completed successfully")
    except Exception as e:
        error_msg = f"Error running PyWake simulation: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

    try:
        # Calculate flow map only if requested
        flow_map = None
        if calculate_flow_map:
            logger.info("Calculating flow map with simplified wind conditions")
            simplified_conditions = create_simplified_wind_conditions(
                wind_conditions, top_n=10)
            flow_map, _ = run_simplified_flow_map_simulation(
                simplified_conditions, turbines_geojson, turbine_model)
            logger.info("Flow map calculation completed")

        # Calculate AEP with wake effects
        logger.info("Calculating Annual Energy Production (AEP)")
        aep_result = sim_result.aep()
        total_aep = float(aep_result.sum())
        aep_per_turbine = aep_result.sum(['wd', 'ws']).values
        logger.info(f"Total AEP: {total_aep:.2f} GWh/year")

        # Calculate wake loss percentage
        logger.info("Calculating wake losses")
        net_aep = sim_result.aep().sum()
        gross_aep = sim_result.aep(with_wake_loss=False).sum()
        wake_loss_percent = 100 * \
            (1 - net_aep / gross_aep) if gross_aep > 0 else 0.0
        logger.info(f"Wake loss: {wake_loss_percent:.2f}%")

        # Calculate capacity factor
        logger.info("Calculating capacity factor")
        rated_power = 3.35
        capacity_factor = (total_aep * 1000) / (len(turbine_positions)
                                                * rated_power * 8760) if total_aep > 0 else 0.0
        logger.info(f"Capacity factor: {capacity_factor:.2%}")
    except Exception as e:
        error_msg = f"Error calculating simulation results: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

    try:
        # Generate unique simulation ID for caching
        logger.info("Generating simulation ID and caching results")
        sim_id = hashlib.sha384(
            f"{total_aep}_{len(turbine_positions)}_{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        logger.info(f"Generated simulation ID: {sim_id}")

        # Cache complex objects for report generation
        logger.info("Caching simulation objects for report generation")
        SIMULATION_CACHE[sim_id] = {
            "flow_map_using_top_x_wind_conditions": flow_map,
            "aep": aep_result,
            "sim_result": sim_result,
            "turbine": turbine,
            "x_positions": x_positions,
            "y_positions": y_positions,
            "aep_per_turbine_gwh": aep_per_turbine.tolist(),
            "wind_conditions": wind_conditions,
            "total_aep_gwh": total_aep,
            "capacity_factor": float(capacity_factor),
            "wake_loss_percent": float(wake_loss_percent),
            "number_of_turbines": len(turbine_positions),
            "mean_wind_speed": float(wind_conditions.get('mean_wind_speed', 0)),
            "turbine_model": "IEA37 3.35MW",
            "aep_values": aep_result.sum(['wd', 'ws']).values.tolist(),
            "has_flow_map": flow_map is not None,
            "project_id": project_id,
            "timestamp": datetime.now().isoformat()
        }
        logger.info(
            f"Cache updated, current keys: {list(SIMULATION_CACHE.keys())}")

        # Return only standard Python types
        logger.info("Preparing final results")
        results = {
            "simulation_id": sim_id,
            "total_aep_gwh": total_aep,
            "aep_per_turbine_gwh": aep_per_turbine.tolist(),
            "capacity_factor": float(capacity_factor),
            "wake_loss_percent": float(wake_loss_percent),
            "number_of_turbines": len(turbine_positions),
            "mean_wind_speed": float(wind_conditions.get('mean_wind_speed', 0)),
            "turbine_model": "IEA37 3.35MW",
            "x_positions": x_positions.tolist(),
            "y_positions": y_positions.tolist(),
            "aep_values": aep_result.sum(['wd', 'ws']).values.tolist(),
            "has_flow_map": flow_map is not None
        }

        logger.info("Wake simulation completed successfully")
        return results
    except Exception as e:
        error_msg = f"Error finalizing simulation results: {str(e)}"
        logger.warning(error_msg)
        raise Exception(error_msg)


@tool
def generate_charts_and_csv(project_id: str, simulation_id: str) -> Dict:
    """
    Generate individual wind farm analysis charts and save each as separate PNG files.

    Creates 8 separate chart files: AEP distribution, wake map, wind rose,
    turbine performance, wake losses, wind speed distribution, power curve,
    and AEP vs wind speed analysis.
    Save output dataframe in a CSV.


    Args:
        project_id (str): unique identifier from terrain analysis
        simulation_id (str): Simulation ID from wake simulation results

    Returns:
        Dict containing success status and list of generated files
    """
    logger.info(f"Generating charts for simulation_id: {simulation_id}")

    try:
        # Get cached data
        if simulation_id not in SIMULATION_CACHE:
            return {
                "success": False,
                "error": f"Simulation ID {simulation_id} not found in cache"
            }

        cached_data = SIMULATION_CACHE[simulation_id]

        # Extract required data from the cache
        sim_result = cached_data.get('sim_result')
        turbine = cached_data.get('turbine')
        x_positions = cached_data.get('x_positions')
        y_positions = cached_data.get('y_positions')
        aep = cached_data.get('aep')
        flow_map = cached_data.get('flow_map_using_top_x_wind_conditions')
        aep_per_turbine = cached_data.get('aep_per_turbine_gwh')
        wind_conditions = cached_data.get('wind_conditions')

        generated_files = []

        # 1. AEP Distribution Chart
        plt.figure(figsize=(8, 6))
        x_min, x_max = min(x_positions) - 100, max(x_positions) + 100
        y_min, y_max = min(y_positions) - 100, max(y_positions) + 100
        if turbine and aep is not None:
            c = plt.scatter(x_positions, y_positions, c=aep.sum(
                ['wd', 'ws']).values, cmap='viridis')
            plt.colorbar(c, label='AEP [GWh]')
        else:
            plt.scatter(x_positions, y_positions,
                        c=aep_per_turbine, cmap='viridis')
            plt.colorbar(label='AEP [GWh]')
        plt.title('AEP Distribution of each turbine')
        plt.xlabel('x [m]')
        plt.ylabel('y [m]')
        plt.xlim([x_min, x_max])
        plt.ylim([y_min, y_max])
        filename = "aep_distribution.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)

        generated_files.append(filename)
        plt.close()

        # 2. Wake Map
        plt.figure(figsize=(8, 6))
        if flow_map is not None:
            flow_map.plot_wake_map()
            plt.title('Wake Map (Top Wind Conditions)')
        else:
            plt.text(0.5, 0.5, 'Flow map not available', ha='center',
                     va='center', transform=plt.gca().transAxes)
            plt.title('Wake Map')
        filename = "wake_map.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
        generated_files.append(filename)
        plt.close()

        # 3. Wind Rose
        fig, ax = plt.subplots(
            figsize=(8, 8), subplot_kw=dict(projection='polar'))
        wd = np.arange(0, 360, 360/len(wind_conditions['p_wd']))
        ax.bar(np.radians(wd), wind_conditions['p_wd'], width=np.radians(
            360/len(wind_conditions['p_wd'])), bottom=0.0)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_title('Wind Rose')
        filename = "wind_rose.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")

        generated_files.append(filename)
        plt.close()

        # 4. AEP per Turbine
        plt.figure(figsize=(10, 6))
        plt.bar(range(0, len(aep_per_turbine)), aep_per_turbine)
        plt.title('Annual Energy Production per Turbine')
        plt.xlabel('Turbine Number')
        plt.ylabel('AEP (GWh)')
        filename = "aep_per_turbine.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
        generated_files.append(filename)
        plt.close()

        # 5. Wake Losses per Turbine
        plt.figure(figsize=(10, 6))
        if sim_result is not None:
            aep_with_wake = sim_result.aep().sum(['wd', 'ws']).values
            aep_no_wake = sim_result.aep(
                with_wake_loss=False).sum(['wd', 'ws']).values
            wake_losses = (aep_no_wake - aep_with_wake) / aep_no_wake * 100
            plt.bar(range(0, len(wake_losses)), wake_losses)
        else:
            wake_loss_per_turbine = [10.0] * len(aep_per_turbine)
            plt.bar(range(0, len(wake_loss_per_turbine)),
                    wake_loss_per_turbine)
        plt.title('Wake Losses per Turbine')
        plt.xlabel('Turbine Number')
        plt.ylabel('Wake Loss (%)')
        filename = "wake_losses.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
        generated_files.append(filename)
        plt.close()

        # 6. Wind Speed Distribution
        plt.figure(figsize=(8, 6))
        ws = np.linspace(0, 30, 100)
        for i in range(min(5, len(wind_conditions['a']))):
            plt.plot(ws, stats.weibull_min.pdf(ws, wind_conditions['k'][i], scale=wind_conditions['a'][i]),
                     label=f'Sector {i+1}')
        plt.title('Wind Speed Distribution per Sector')
        plt.xlabel('Wind Speed (m/s)')
        plt.ylabel('Probability Density')
        plt.legend()
        filename = "wind_speed_distribution.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
        generated_files.append(filename)
        plt.close()

        # 7. Power Curve
        plt.figure(figsize=(8, 6))
        ws = np.linspace(0, 30, 100)
        if turbine:
            power = turbine.power(ws)
            plt.plot(ws, power)
        else:
            power = np.where(ws < 3, 0, np.where(
                ws < 15, 3.35 * ((ws - 3) / 12) ** 3, 3.35))
            power = np.where(ws > 25, 0, power)
            plt.plot(ws, power)
        plt.title('Turbine Power Curve')
        plt.xlabel('Wind Speed (m/s)')
        plt.ylabel('Power (MW)')
        plt.grid(True)
        filename = "power_curve.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
        generated_files.append(filename)
        plt.close()

        # 8. AEP vs Wind Speed
        plt.figure(figsize=(8, 6))
        if aep is not None:
            plt.plot(aep.sum(['wt', 'wd']))
        else:
            ws_range = np.arange(3, 26)
            aep_approx = [sum(aep_per_turbine) * (ws/15) **
                          2 * np.exp(-(ws/10)) for ws in ws_range]
            plt.plot(ws_range, aep_approx)
        plt.title('AEP vs Wind Speed')
        plt.xlabel("Wind Speed [m/s]")
        plt.ylabel("AEP [GWh]")
        plt.grid(True)
        filename = "aep_vs_windspeed.png"
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight')
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
        generated_files.append(filename)
        plt.close()

        # 9.Saving raw data CSV
        df = sim_result.to_dataframe()           # Convert to DataFrame
        csv_buffer = io.StringIO()
        # Maintain index if you want coordinates in CSV
        df.to_csv(csv_buffer, index=True)
        csv_str = csv_buffer.getvalue()          # Fetch CSV as string

        filename = "raw_output_data.csv"
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as temp_file:
            temp_file.write(csv_str.encode())   # Write CSV string to file
            temp_file.flush()
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
            print(f"===saving")

        generated_files.append(filename)

        # 10. Saving Simulation Cache
        sim_id_data = SIMULATION_CACHE[simulation_id]

        serializable_summary = {
            "aep_per_turbine_gwh": list(sim_id_data["aep_per_turbine_gwh"]),
            "total_aep_gwh": float(sim_id_data["total_aep_gwh"]),
            "capacity_factor": float(sim_id_data["capacity_factor"]),
            "wake_loss_percent": float(sim_id_data["wake_loss_percent"]),
            "number_of_turbines": int(sim_id_data["number_of_turbines"]),
            "mean_wind_speed": float(sim_id_data["mean_wind_speed"]),
            "turbine_model": str(sim_id_data["turbine_model"]),
            "aep_values": list(sim_id_data["aep_values"]),
            "has_flow_map": bool(sim_id_data["has_flow_map"])
        }

        filename = "simulation_summary.json"
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w', encoding='utf-8') as temp_file:
            # Serialize dict to JSON and write to file
            json.dump(serializable_summary, temp_file, indent=4)
            temp_file.flush()  # Ensure data is written to disk
            temp_file.close()
            # ok:tempfile-without-flush
            save_file_with_storage(
                temp_file.name, project_id, filename, "file_copy", "simulation_agent")
            # ok:tempfile-without-flush
            os.unlink(temp_file.name)
            print(f"===saving")

        logger.info(f"Generated {len(generated_files)} individual chart files")
        return {
            "success": True,
            "generated_files": generated_files,
            "project_id": project_id,
            "message": f"Generated {len(generated_files)} individual chart files successfully"
        }

    except Exception as e:
        logger.error(f"Error generating charts: {str(e)}", exc_info=True)
        plt.close('all')
        return {
            "success": False,
            "error": f"Failed to generate charts: {str(e)}"
        }
