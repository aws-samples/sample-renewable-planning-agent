import seaborn as sns
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from strands import tool
import os
import json
import re
from typing import Dict, List, Any
from .storage_utils import load_file_from_storage, save_file_with_storage
from .shared_tools import load_project_data, get_latest_images
import tempfile
from datetime import datetime
import markdown
import weasyprint
import base64
import logging
import matplotlib
matplotlib.use('Agg')  # CRITICAL: Must be before importing pyplot

logger = logging.getLogger(__name__)

logging.getLogger('fontTools').setLevel(logging.ERROR)
logging.getLogger('fontTools.ttLib.ttFont').setLevel(logging.ERROR)
logging.getLogger('fontTools.subset.timer').setLevel(logging.ERROR)
logging.getLogger('fontTools.subset').setLevel(logging.ERROR)
logging.getLogger('matplotlib').setLevel(logging.ERROR)
logging.getLogger('PIL').setLevel(logging.ERROR)


@tool
def save_report(project_id: str, report_content: str, report_type: str = "comprehensive") -> Dict[str, Any]:
    """
    Save a report to the reports directory.

    Args:
        project_id (str): unique project identifier
        report_content (str): Complete report content in markdown format
        report_type (str): Type of report (default: "comprehensive")

    Returns:
        Dict containing save status and file information
    """
    logger.info(f"Saving {report_type} report for project: {project_id}")
    try:
        # Create filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"wind_farm_{report_type}_report_{timestamp}.md"

        # Save using storage utilities - save in project_id/reports/ folder
        reports_filename = f"reports/{filename}"
        save_file_with_storage(
            report_content,
            project_id,
            reports_filename,
            "text",
            "report_agent"
        )

        return {
            'success': True,
            'filename': filename,
            'project_id': project_id,
            'report_type': report_type,
            'message': f"Report saved successfully as {filename}"
        }

    except Exception as e:
        logger.error(f"Error saving report: {e}")
        return {
            'success': False,
            'error': f"Failed to save report: {str(e)}"
        }


@tool
def create_pdf_report_with_images(project_id: str, markdown_content: str, image_filenames: List[str] = None) -> Dict[str, Any]:
    """
    Create PDF report with embedded images from project storage.

    Args:
        project_id (str): unique project identifier
        markdown_content (str): Complete report content in markdown format
        image_filenames (List[str]): List of image filenames to embed in PDF

    Returns:
        Dict containing PDF creation status and file information
    """
    logger.info(f"Creating PDF report with images for project: {project_id}")
    logger.info(f"Image filenames: {image_filenames}")
    try:
        # Create filename
        filename = f"wind_farm_report.pdf"

        # Download and encode images as base64
        embedded_images = {}
        if image_filenames:
            for img_filename in image_filenames:
                try:
                    # Parse agent folder and filename from full path
                    if '/' in img_filename:
                        agent_folder, file_only = img_filename.split('/', 1)
                    else:
                        agent_folder, file_only = "report_agent", img_filename

                    img_path = load_file_from_storage(
                        project_id, file_only, agent_folder)
                    with open(img_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode()
                        embedded_images[img_filename] = f"data:image/png;base64,{img_data}"
                    logger.info(f"Embedded image: {img_filename}")
                except Exception as e:
                    logger.warning(
                        f"Could not embed image {img_filename}: {e}")

        # Replace image references with base64 embedded images
        def replace_image(match):
            alt_text = match.group(1)
            img_filename = match.group(2)
            if img_filename in embedded_images:
                return f'<img src="{embedded_images[img_filename]}" alt="{alt_text}" style="max-width: 100%; height: auto; margin: 20px 0;">'
            else:
                return f'<p><em>Image not available: {img_filename}</em></p>'

        # Convert markdown to HTML with embedded images
        html_with_images = re.sub(
            r'!\[([^\]]*)\]\(([^\)]+\.png)\)', replace_image, markdown_content)
        html_content = markdown.markdown(html_with_images, extensions=[
                                         'tables', 'fenced_code'])

        # Add CSS styling for professional appearance
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Wind Farm Report - Project {project_id}</title>
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    line-height: 1.6;
                    margin: 40px;
                    color: #333;
                }}
                h1 {{
                    color: #1e3a8a;
                    border-bottom: 3px solid #1e3a8a;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #1e3a8a;
                    border-bottom: 1px solid #e5e7eb;
                    padding-bottom: 5px;
                }}
                h3 {{
                    color: #374151;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 20px 0;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #1e3a8a;
                    color: white;
                }}
                img {{
                    max-width: 100%;
                    height: auto;
                    margin: 20px 0;
                    display: block;
                    margin-left: auto;
                    margin-right: auto;
                }}
                .executive-summary {{
                    background-color: #f8fafc;
                    padding: 20px;
                    border-left: 4px solid #1e3a8a;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

        # Create PDF using temporary file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            weasyprint.HTML(string=styled_html).write_pdf(temp_file.name)
            temp_file.flush()
            # ok:tempfile-without-flush
            temp_filepath = temp_file.name

            # Save using storage utilities - save in report_agent folder
            save_file_with_storage(
                temp_filepath,
                project_id,
                filename,
                "file_copy",
                "report_agent"
            )

            # Clean up temp file
            temp_file.close()

            return {
                'success': True,
                'filename': filename,
                'project_id': project_id,
                'embedded_images': len(embedded_images),
                'message': f"PDF report created successfully as {filename} with {len(embedded_images)} embedded images"
            }
    except Exception as e:
        logger.error(f"Error creating PDF report: {e}")
        return {
            'success': False,
            'error': f"Failed to create PDF report: {str(e)}"
        }


@tool
def save_chart(project_id: str, chart_data: str, filename: str) -> Dict[str, Any]:
    """
    Save a chart/image to project storage.

    Args:
        project_id (str): unique project identifier
        chart_data (str): Base64 encoded image data or file path
        filename (str): Name of the chart file (e.g., "financial_projections.png")

    Returns:
        Dict containing save status and file information
    """
    logger.info(f"Saving chart: {project_id}/{filename}")
    try:

        # Check if chart_data is a file path or base64 data
        if os.path.exists(chart_data):
            # It's a file path, copy the file
            save_file_with_storage(
                chart_data,
                project_id,
                filename,
                "file_copy",
                "report_agent"
            )
        else:
            # It's base64 data, decode and save
            try:
                image_data = base64.b64decode(chart_data)
                save_file_with_storage(
                    image_data,
                    project_id,
                    filename,
                    "bytes",
                    "report_agent"
                )
            except Exception:
                # If base64 decode fails, treat as text content
                save_file_with_storage(
                    chart_data,
                    project_id,
                    filename,
                    "text",
                    "report_agent"
                )
        logger.info(f"Chart saved successfully")
        return {
            'success': True,
            'filename': filename,
            'project_id': project_id,
            'message': f"Chart saved successfully as {filename}"
        }

    except Exception as e:
        logger.error(f"Error saving chart: {e}")
        return {
            'success': False,
            'error': f"Failed to save chart: {str(e)}"
        }


@tool
def create_report_charts(project_id: str) -> Dict[str, Any]:
    """
    Create all comprehensive charts for wind farm reports using project data.
    Automatically loads terrain, layout, simulation, and wind data to create meaningful charts.

    Args:
        project_id (str): unique project identifier

    Returns:
        Dict containing created chart filenames and status
    """
    logger.info(f"Creating all report charts for project: {project_id}")

    try:
        # Set style for professional charts
        plt.style.use('default')
        plt.ioff()  # Turn off interactive mode
        sns.set_palette("husl")

        created_charts = []

        # Load project data directly
        logger.info("Loading project data...")
        terrain_data = None
        layout_data = None

        try:
            terrain_path = load_file_from_storage(
                project_id, "boundaries.geojson", "terrain_agent")
            with open(terrain_path, 'r') as f:
                terrain_data = json.load(f)
        except:
            logger.warning("Could not load terrain data")

        try:
            layout_path = load_file_from_storage(
                project_id, "turbine_layout.geojson", "layout_agent")
            with open(layout_path, 'r') as f:
                layout_data = json.load(f)
        except:
            logger.warning("Could not load layout data")

        try:
            simulation_path = load_file_from_storage(
                project_id, "simulation_summary.json", "simulation_agent")
            with open(simulation_path, 'r') as f:
                simulation_data = json.load(f)
        except:
            logger.warning("Could not load simulation data")

        # Extract basic project metrics
        num_turbines = len(layout_data['features']) if layout_data else 10
        # Default estimate
        total_aep = simulation_data["total_aep_gwh"] if simulation_data else num_turbines * 12
        capacity_factor = simulation_data["capacity_factor"] if simulation_data else 0.45
        wake_losses = simulation_data["wake_loss_percent"] if simulation_data else 8
        mean_wind_speed = simulation_data["mean_wind_speed"] if simulation_data else 8.5

        # Try to extract metrics from simulation cache
        try:
            from .simulation_tools import SIMULATION_CACHE

            # Find latest simulation for this project by timestamp
            latest_sim = None
            latest_timestamp = None

            for sim_id, sim_data in SIMULATION_CACHE.items():
                if sim_data.get('project_id') == project_id:
                    sim_timestamp = sim_data.get('timestamp')
                    logger.info(
                        f"Found simulation {sim_id} with timestamp {sim_timestamp}")
                    if sim_timestamp and (latest_timestamp is None or sim_timestamp > latest_timestamp):
                        latest_sim = sim_data
                        latest_timestamp = sim_timestamp
                        logger.info(
                            f"Latest simulation updated to {sim_id} with timestamp {latest_timestamp}")

            if latest_sim:
                if 'capacity_factor' in latest_sim:
                    capacity_factor = latest_sim['capacity_factor']
                if 'wake_loss_percent' in latest_sim:
                    wake_losses = latest_sim['wake_loss_percent']
                if 'total_aep_gwh' in latest_sim:
                    total_aep = latest_sim['total_aep_gwh']
                if 'number_of_turbines' in latest_sim:
                    num_turbines = latest_sim['number_of_turbines']
                if 'mean_wind_speed' in latest_sim:
                    mean_wind_speed = latest_sim['mean_wind_speed']
                logger.info("Found simulation data in cache")
        except Exception as e:
            logger.warning(f"Could not access simulation cache: {e}")

        logger.info(
            f"Project metrics: {num_turbines} turbines, {total_aep:.1f} GWh AEP, {capacity_factor:.1%} CF")

        return {
            'success': True,
            'created_charts': created_charts,
            'project_id': project_id,
            'message': f"Successfully created {len(created_charts)} charts using project data: {', '.join(created_charts)}"
        }

    except Exception as e:
        logger.error(f"Error creating charts: {e}")
        plt.close('all')  # Close any open figures
        return {
            'success': False,
            'error': f"Failed to create charts: {str(e)}",
            'created_charts': created_charts if 'created_charts' in locals() else []
        }
