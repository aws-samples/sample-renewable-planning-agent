import os
from boto3 import session

from strands.models import BedrockModel
from strands import Agent, tool
from strands.handlers.callback_handler import PrintingCallbackHandler

from tools.terrain_tools import get_unbuildable_areas
from prompts.terrain_prompt import TERRAIN_AGENT_SYSTEM_PROMPT
from tools.shared_tools import get_turbine_specs
from tools.knowledge_base_tools import query_knowledge_base
from logging_config import get_logger

# Configure logging
logger = get_logger('terrain_agent')
region_name = os.environ.get('AWS_REGION', 'us-west-2')
model_id = os.environ.get(
    'MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0')

logger.info(
    f"Initializing terrain_agent with region: {region_name}, model: {model_id}")

tools = [get_unbuildable_areas, get_turbine_specs, query_knowledge_base]

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
    )
)

callback_handler = PrintingCallbackHandler()
if os.getenv("DISABLE_CALLBACK_HANDLER"):
    callback_handler = None

terrain_agent = Agent(
    callback_handler=callback_handler,
    tools=tools,
    model=bedrock_model,
    system_prompt=TERRAIN_AGENT_SYSTEM_PROMPT
)


@tool  # This decorator transforms a Python function into a Strands tool.
def terrain_agent_as_tool(query="No prompt found in input, please guide customer to create a json payload with prompt key") -> str:
    """Performs terrain analysis in wind farm projects for a given location with latitude and longitude coordinates."""
    return terrain_agent(query)
