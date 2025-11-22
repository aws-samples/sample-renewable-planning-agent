# Wind Farm Planning Assistant 🌪️

An AI-powered multi-agent system for comprehensive wind farm development, from site analysis to energy production simulation.

## Overview

This project provides specialized AI agents that work together to analyze terrain, design optimal turbine layouts, and simulate wind farm performance using Amazon Bedrock and advanced wind modeling tools.

## Features

- **🗺️ Terrain Analysis**: Identify un-buildable areas and exclusion zones
- **📐 Layout Optimization**: Design optimal turbine placements with safety setbacks
- **⚡ Energy Simulation**: Calculate annual energy production and wake effects
- **📊 Executive Reports**: Generate comprehensive analysis reports with visualizations

## Architecture

### Agents

- **Terrain Analysis Agent**: Analyzes geographic constraints and exclusion zones
- **Layout Agent**: Designs optimal turbine layouts considering terrain and regulations
- **Simulation Agent**: Performs wake modeling and energy production calculations
- **Report Agent**: Generates executive summaries and visualizations
- **Multi-Agent**: Orchestrates the complete workflow

### Key Technologies

- **Amazon Bedrock**: Claude Sonnet 4 for AI reasoning
- **Amazon Bedrock AgentCore**: Secure scalable runtime for agent deployment
- **Strands Agents**: Agent development framework
- **MCP (Model Context Protocol)**: Tool integration
- **PyWake**: Advanced wake modeling and yield simulation
- **Folium/GeoPandas**: Geo-spatial visualization

## Quick Start

### Prerequisites

- Python 3.12-3.13
- AWS credentials configured
- Access to Claude Sonnet via Bedrock

### Installation

```bash
# Clone the repository
git clone <repository-url>

# Install dependencies using uv
uv sync

# Or using pip
pip install -e .
```

### Configuration

Set environment variables:

```bash
export AWS_REGION=us-west-2
export NREL_API_KEY=<api_key>
export INTERACTIVE_MODE=1           # For interactive CLI mode
export USE_LOCAL_MCP=1              # Used with the local MCP Server
export GET_INFO_LOGS=1              # Used to see more logs
export DISABLE_CALLBACK_HANDLER=1   # Stop callback from the specialized agents
```

### Storage

The Agent can store the assets locally or they can also use S3 (local is the default). In order to use S3, you need to use the following SSM parameters:

```sh
aws ssm put-parameter --name "/wind-farm-assistant/s3-bucket-name" --value "your-bucket-name" --type "String"
aws ssm put-parameter --name "/wind-farm-assistant/use-s3-storage" --value "true" --type "String"
```

## Project Structure

```sh
root/
├── agents/                   # AI agent implementations
│   ├── prompts/              # System prompts used by the agents
│   ├── tools/                # Agent-specific tools
│   ├── terrain_agent.py
│   ├── layout_agent.py
│   ├── simulation_agent.py
│   └── reporting_agent.py
├── mcp_tools/               # MCP server for tool integration
├── assets/                   # Outputs: Generated maps and layouts
└── web_app/               # Web application interface
```

## Example Workflow

1. **Terrain Analysis**

   ```text
   Analyze terrain at 35.067482, -101.395466 with turbine model "IEA_Reference_3.4MW_130"
   ```

2. **Layout Design**

   ```text
   Create a 30MW wind farm at location lat:35.067482, lon:-101.395466 using IEA_Reference_3.4MW_130 turbines for project_id 1111_2222
   ```

3. **Energy Simulation**

   ```text
   Run wake simulation for the layout with wind conditions 
   at coordinates 35.067482, -101.395466
   ```

4. **Report Generation**

   ```text
   Generate executive report with charts and recommendations
   ```

## Output Files

- **Maps**: `assets/<project_id>/terrain_agent/` - Satellite imagery, terrain maps, layout visualizations
- **Layouts**: `assets/<project_id>/layout_agent/` - GeoJSON turbine layouts
- **Reports**: `assets/<project_id>/report_agent/` - Executive analysis reports
- **Simulations**: `assets/<project_id>/simulation_agent/` Cached simulation results and flow maps

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For questions, issues, or feature requests:

- Open an issue
- Check the tutorial notebooks for examples
- Review individual agent documentation

## 🙏 Acknowledgments

- **NREL** for wind resource data and turbine data
- **OverpassAPI** and OpenStreetMaps for the map features
- **PyWake** for wake modeling capabilities
- **Strands SDK** for multi-agent framework
- **AWS Bedrock** for AI inference
- **USGS/ArcGIS** for satellite imagery

---

~Built with ❤️ for the renewable energy community~
