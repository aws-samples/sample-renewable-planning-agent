import os
from boto3 import session

from strands.models import BedrockModel
from strands import Agent, tool
from strands_tools import current_time
from strands.handlers.callback_handler import PrintingCallbackHandler

from agents.tools.report_tools import create_pdf_report_with_images, create_report_charts
from agents.prompts.report_prompt import REPORT_AGENT_SYSTEM_PROMPT
from agents.tools.shared_tools import list_project_files, load_project_data, get_latest_images, analyze_simulation_results
from agents.logging_config import get_logger

# Configure logging
logger = get_logger('layout_agent')

# Remove prompt for user confirmation before executing
os.environ["BYPASS_TOOL_CONSENT"] = "true"
region_name = os.environ.get('AWS_REGION', 'us-west-2')
model_id = os.environ.get(
    'MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0')

logger.info(
    f"Initializing report_agent with region: {region_name}, model: {model_id}")

tools = [
    list_project_files,
    load_project_data,
    get_latest_images,
    # create_report_charts,
    analyze_simulation_results,
    create_pdf_report_with_images,
    current_time,
]

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

# Create the Strands agent
report_agent = Agent(
    callback_handler=callback_handler,
    tools=tools,
    model=bedrock_model,
    system_prompt=REPORT_AGENT_SYSTEM_PROMPT
)


@tool
def report_agent_as_tool(query="No prompt found in input, please guide customer to create a json payload with prompt key") -> str:
    """Initialize the Report agent"""
    return report_agent(query)
