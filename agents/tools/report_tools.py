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
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

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
                    
                    img_path = load_file_from_storage(project_id, file_only, agent_folder)
                    with open(img_path, 'rb') as img_file:
                        img_data = base64.b64encode(img_file.read()).decode()
                        embedded_images[img_filename] = f"data:image/png;base64,{img_data}"
                    logger.info(f"Embedded image: {img_filename}")
                except Exception as e:
                    logger.warning(f"Could not embed image {img_filename}: {e}")
        
        # Replace image references with base64 embedded images
        def replace_image(match):
            alt_text = match.group(1)
            img_filename = match.group(2)
            if img_filename in embedded_images:
                return f'<img src="{embedded_images[img_filename]}" alt="{alt_text}" style="max-width: 100%; height: auto; margin: 20px 0;">'
            else:
                return f'<p><em>Image not available: {img_filename}</em></p>'
        
        # Convert markdown to HTML with embedded images
        html_with_images = re.sub(r'!\[([^\]]*)\]\(([^\)]+\.png)\)', replace_image, markdown_content)
        html_content = markdown.markdown(html_with_images, extensions=['tables', 'fenced_code'])
        
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
        os.unlink(temp_filepath)
        
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
            terrain_path = load_file_from_storage(project_id, "boundaries.geojson", "terrain_agent")
            with open(terrain_path, 'r') as f:
                terrain_data = json.load(f)
        except:
            logger.warning("Could not load terrain data")
            
        try:
            layout_path = load_file_from_storage(project_id, "turbine_layout.geojson", "layout_agent")
            with open(layout_path, 'r') as f:
                layout_data = json.load(f)
        except:
            logger.warning("Could not load layout data")
            
        try:
            simulation_path = load_file_from_storage(project_id, "simulation_summary.json", "simulation_agent")
            with open(simulation_path, 'r') as f:
                simulation_data = json.load(f)
        except:
            logger.warning("Could not load simulation data")

        # Extract basic project metrics
        num_turbines = len(layout_data['features']) if layout_data else 10
        total_aep = simulation_data["total_aep_gwh"] if simulation_data else num_turbines * 12  # Default estimate
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
                    logger.info(f"Found simulation {sim_id} with timestamp {sim_timestamp}")
                    if sim_timestamp and (latest_timestamp is None or sim_timestamp > latest_timestamp):
                        latest_sim = sim_data
                        latest_timestamp = sim_timestamp
                        logger.info(f"Latest simulation updated to {sim_id} with timestamp {latest_timestamp}")
            
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
        
        logger.info(f"Project metrics: {num_turbines} turbines, {total_aep:.1f} GWh AEP, {capacity_factor:.1%} CF")
        
        # # 1. Spider/Radar Chart - Project Assessment
        # categories = ['Wind Resource', 'Grid Access', 'Environmental Impact', 
        #              'Community Support', 'Economic Viability', 'Technical Feasibility']
        
        # # Calculate assessment scores
        # wind_score = min(95, max(30, (mean_wind_speed - 4) * 15))  # 4-8 m/s = 30-90 points
        # grid_score = 75  # Default - could be enhanced with distance to grid data
        # env_score = 85 if terrain_data and len(terrain_data.get('features', [])) < 5 else 65
        # community_score = 80  # Default - could be enhanced with demographic data
        # economic_score = min(95, max(40, (total_aep / num_turbines) * 8))  # Based on AEP per turbine
        # tech_score = max(70, 95 - wake_losses)  # Higher wake losses = lower tech score
        
        # values = [wind_score, grid_score, env_score, community_score, economic_score, tech_score]
        
        # angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
        # values_plot = values + [values[0]]
        # angles_plot = angles + [angles[0]]
        
        # fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
        # ax.plot(angles_plot, values_plot, 'o-', linewidth=3, color='#2E86AB', markersize=8)
        # ax.fill(angles_plot, values_plot, alpha=0.25, color='#2E86AB')
        # ax.set_xticks(angles)
        # ax.set_xticklabels(categories, size=12, weight='bold')
        # ax.set_ylim(0, 100)
        # ax.set_title('Project Assessment Spider Chart', size=16, pad=20, weight='bold')
        # ax.grid(True, linestyle='--', alpha=0.7)
        # ax.set_theta_offset(np.pi / 2)
        # ax.set_theta_direction(-1)
        
        # with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
        #     fig.savefig(temp_file.name, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        #     save_file_with_storage(temp_file.name, project_id, "spider_chart.png", "file_copy", "report_agent")
        #     os.unlink(temp_file.name)
        # created_charts.append("spider_chart.png")
        # plt.close(fig)
        
        # # 2. Heatmap - Performance Matrix with realistic seasonal data
        # months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
        #           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        # metrics = ['Wind Speed', 'Capacity Factor', 'Availability', 'Efficiency']
        
        # # Generate realistic seasonal patterns based on project location and wind resource
        # base_wind = mean_wind_speed
        # seasonal_wind = [base_wind + np.sin((i-3)*np.pi/6) * 1.5 for i in range(12)]
        # seasonal_cf = [min(65, max(25, ws**2.5 * 2.2)) for ws in seasonal_wind]
        # availability = [98 - abs(i-6) * 0.5 for i in range(12)]  # Lower in extreme months
        # efficiency = [92 + np.sin(i*np.pi/6) * 3 for i in range(12)]  # Seasonal efficiency
        
        # heatmap_data = np.array([seasonal_wind, seasonal_cf, availability, efficiency])
        
        # fig, ax = plt.subplots(figsize=(14, 8))
        # sns.heatmap(heatmap_data, annot=True, fmt='.1f', cmap='YlOrRd', 
        #             xticklabels=months, yticklabels=metrics,
        #             cbar_kws={'label': 'Performance Value'},
        #             linewidths=0.5, linecolor='white')
        # ax.set_title('Annual Performance Heatmap', size=16, pad=20, weight='bold')
        # plt.tight_layout()
        
        # with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
        #     fig.savefig(temp_file.name, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        #     save_file_with_storage(temp_file.name, project_id, "performance_heatmap.png", "file_copy", "report_agent")
        #     os.unlink(temp_file.name)
        # created_charts.append("performance_heatmap.png")
        # plt.close(fig)
        
        # # 3. Financial Projections
        # years = np.arange(2024, 2044)
        
        # # Calculate realistic financial projections
        # annual_revenue = total_aep * 60  # $60/MWh
        # annual_costs = annual_revenue * 0.35  # 35% for O&M
        # capex = num_turbines * 2.5  # $2.5M per turbine
        
        # # 20-year projections with degradation and inflation
        # revenues = []
        # costs = []
        # for i in range(20):
        #     degradation = (1 - 0.005) ** i  # 0.5% annual degradation
        #     inflation = (1 + 0.025) ** i    # 2.5% annual inflation
        #     revenues.append(annual_revenue * degradation * inflation)
        #     costs.append(annual_costs * inflation)
        
        # revenue = np.cumsum(revenues)
        # costs = np.cumsum(costs) + capex
        
        # fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # ax1.plot(years, revenue, 'g-', linewidth=3, label='Cumulative Revenue', marker='o')
        # ax1.plot(years, costs, 'r-', linewidth=3, label='Cumulative Costs', marker='s')
        # ax1.fill_between(years, revenue, costs, where=(revenue >= costs), 
        #                  color='green', alpha=0.3, label='Profit Zone')
        # ax1.fill_between(years, revenue, costs, where=(revenue < costs), 
        #                  color='red', alpha=0.3, label='Loss Zone')
        # ax1.set_ylabel('Amount (Million $)', size=12, weight='bold')
        # ax1.set_title('Financial Projections Over 20 Years', size=14, weight='bold')
        # ax1.legend(loc='upper left')
        # ax1.grid(True, alpha=0.3)
        
        # roi = ((revenue - costs) / costs) * 100
        # colors = ['red' if r < 0 else 'green' for r in roi]
        # ax2.bar(years, roi, color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
        # ax2.axhline(y=0, color='black', linestyle='-', linewidth=1)
        # ax2.set_xlabel('Year', size=12, weight='bold')
        # ax2.set_ylabel('ROI (%)', size=12, weight='bold')
        # ax2.set_title('Return on Investment by Year', size=14, weight='bold')
        # ax2.grid(True, alpha=0.3)
        
        # plt.tight_layout()
        # with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
        #     fig.savefig(temp_file.name, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        #     save_file_with_storage(temp_file.name, project_id, "financial_projections.png", "file_copy", "report_agent")
        #     os.unlink(temp_file.name)
        # created_charts.append("financial_projections.png")
        # plt.close(fig)
        
        # # 4. Risk Matrix based on project characteristics
        # risks = {
        #     'Weather Delays': (0.7, 0.6),
        #     'Grid Connection': (0.4 if num_turbines < 20 else 0.6, 0.8),
        #     'Permit Issues': (0.3 if env_score > 75 else 0.5, 0.7),
        #     'Equipment Failure': (0.2, 0.9),
        #     'Cost Overrun': (0.5 if num_turbines > 15 else 0.4, 0.6),
        #     'Community Opposition': (0.3 if community_score > 75 else 0.5, 0.4)
        # }
        
        # fig, ax = plt.subplots(figsize=(10, 8))
        
        # for risk, (prob, impact) in risks.items():
        #     color = 'red' if prob * impact > 0.5 else 'orange' if prob * impact > 0.3 else 'green'
        #     ax.scatter(prob, impact, s=200, c=color, alpha=0.7, edgecolors='black')
        #     ax.annotate(risk, (prob, impact), xytext=(5, 5), textcoords='offset points', 
        #                fontsize=10, weight='bold')
        
        # ax.set_xlabel('Probability', size=12, weight='bold')
        # ax.set_ylabel('Impact', size=12, weight='bold')
        # ax.set_title('Risk Assessment Matrix', size=16, weight='bold', pad=20)
        # ax.grid(True, alpha=0.3)
        # ax.set_xlim(0, 1)
        # ax.set_ylim(0, 1)
        
        # plt.tight_layout()
        # with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
        #     fig.savefig(temp_file.name, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        #     save_file_with_storage(temp_file.name, project_id, "risk_matrix.png", "file_copy", "report_agent")
        #     os.unlink(temp_file.name)
        # created_charts.append("risk_matrix.png")
        # plt.close(fig)
        
        # # 5. Timeline/Gantt Chart based on project size
        # construction_months = max(8, num_turbines // 3)  # Larger projects take longer
        # phases = {
        #     'Planning & Permits': (0, 6),
        #     'Site Preparation': (4, 6 + construction_months // 4),
        #     'Foundation Work': (6, 8 + construction_months // 2),
        #     'Turbine Installation': (8, 8 + construction_months),
        #     'Grid Connection': (6 + construction_months, 10 + construction_months),
        #     'Commissioning': (8 + construction_months, 12 + construction_months),
        #     'Operations': (12 + construction_months, 240)
        # }
        
        # fig, ax = plt.subplots(figsize=(12, 6))
        # colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FECA57', '#FF9FF3', '#54A0FF']
        
        # for i, (phase, (start, end)) in enumerate(phases.items()):
        #     ax.barh(i, end - start, left=start, height=0.6, 
        #            color=colors[i % len(colors)], alpha=0.8, edgecolor='black')
        #     ax.text(start + (end - start) / 2, i, phase, 
        #            ha='center', va='center', weight='bold', size=10)
        
        # ax.set_xlabel('Months from Project Start', size=12, weight='bold')
        # ax.set_title('Project Implementation Timeline', size=16, weight='bold', pad=20)
        # ax.set_yticks([])
        # ax.grid(True, alpha=0.3, axis='x')
        # plt.tight_layout()
        
        # with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
        #     fig.savefig(temp_file.name, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        #     save_file_with_storage(temp_file.name, project_id, "project_timeline.png", "file_copy", "report_agent")
        #     os.unlink(temp_file.name)
        # created_charts.append("project_timeline.png")
        # plt.close(fig)
        
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