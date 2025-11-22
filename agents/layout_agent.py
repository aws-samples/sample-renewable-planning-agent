import logging
import time
import os
from boto3 import session

from mcp import stdio_client, StdioServerParameters
from strands.tools.mcp import MCPClient
from strands.handlers.callback_handler import PrintingCallbackHandler

from strands.models import BedrockModel
from strands import Agent, tool
from agents.tools.streamable_http_sigv4 import streamablehttp_client_with_sigv4

from agents.tools.layout_tools import (
    create_grid_layout, create_offset_grid_layout, create_spiral_layout,
    create_greedy_layout, explore_alternative_sites,
    relocate_conflicting_turbines, relocate_turbines_manually,
    save_layout, load_turbine_layout
)
from agents.prompts.layout_prompt import LAYOUT_AGENT_SYSTEM_PROMPT
from agents.tools.shared_tools import get_turbine_specs
from agents.tools.mcp_utils import get_mcp_config, fetch_access_token, create_streamable_http_transport, get_full_tools_list
from agents.logging_config import get_logger

# Configure logging
logger = get_logger('layout_agent')
region_name = os.environ.get('AWS_REGION', 'us-west-2')
model_id = os.environ.get(
    'MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0')

logger.info(
    f"Initializing layout_agent with region: {region_name}, model: {model_id}")

# Connect to remote MCP server via AgentCore gateway
boto_session = session.Session(region_name=region_name)
ssm = boto_session.client('ssm')
gateway_url = ssm.get_parameter(
    Name='/wind-farm-assistant/gateway_url')['Parameter']['Value']
mcp_client = MCPClient(lambda: streamablehttp_client_with_sigv4(
    url=gateway_url,
    credentials=boto_session.get_credentials(),
    service="bedrock-agentcore",
    region=region_name)
)
mcp_client.__enter__()
mcp_tools = get_full_tools_list(mcp_client)
logger.info(
    f"[Remote MCP] Loaded {len(mcp_tools)} tools from remote MCP server")

# Combine MCP tools with our custom layout tools
custom_tools = [
    get_turbine_specs,
    create_grid_layout,
    create_offset_grid_layout,
    create_spiral_layout,
    create_greedy_layout,
    explore_alternative_sites,
    relocate_conflicting_turbines,
    relocate_turbines_manually,
    save_layout,
    load_turbine_layout
]

# Combine all tools
tools = mcp_tools + custom_tools
logger.info(f"Total tools available: {len(tools)}")

# Create a BedrockModel with custom client config
bedrock_model = BedrockModel(
    model_id=model_id,
    temperature=1,
    boto_client_config=session.Config(
        region_name=region_name,
        read_timeout=300,  # 5 minutes for reading responses
        connect_timeout=60,  # 1 minute for initial connection
        retries={
            'max_attempts': 5,
            'total_max_attempts': 10
        }
    ),
    additional_request_fields={
        "thinking": {
            "type": "enabled",
            "budget_tokens": 4096  # Minimum of 1,024
        }
    }
)

callback_handler = PrintingCallbackHandler()
if os.getenv("DISABLE_CALLBACK_HANDLER"):
    callback_handler = None

# Create the Strands agent
layout_agent = Agent(
    callback_handler=callback_handler,
    tools=tools,
    model=bedrock_model,
    system_prompt=LAYOUT_AGENT_SYSTEM_PROMPT
)


@tool
def layout_agent_as_tool(query="No prompt found in input, please guide customer to create a json payload with prompt key") -> str:
    """Initialize the layout agent"""
    return layout_agent(query)
