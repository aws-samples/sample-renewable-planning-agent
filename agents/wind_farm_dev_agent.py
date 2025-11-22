import os
from boto3 import session

from strands.models import BedrockModel
from strands import Agent, tool
from strands.tools.executors import SequentialToolExecutor
from strands.handlers.callback_handler import PrintingCallbackHandler

from agents.terrain_agent import terrain_agent_as_tool
from agents.layout_agent import layout_agent_as_tool
from agents.simulation_agent import simulation_agent_as_tool
from agents.report_agent import report_agent_as_tool
from agents.tools.wind_farm_dev_tools import generate_project_id, validate_layout_quality, get_project_status, load_layout_image
from agents.tools.shared_tools import load_project_data, get_latest_images, analyze_simulation_results
from agents.prompts.development_agent_prompt import DEVELOPMENT_AGENT_SYSTEM_PROMPT
from agents.logging_config import get_logger

# Used for AgentCore
from bedrock_agentcore.runtime import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

logger = get_logger('wind_farm_dev_agent')
region_name = os.environ.get('AWS_REGION', 'us-west-2')
model_id = os.environ.get(
    'MODEL_ID', 'us.anthropic.claude-sonnet-4-20250514-v1:0')

logger.info(
    f"Initializing agent with region: {region_name}, model: {model_id}")

tools = [
    terrain_agent_as_tool,  # Terrain agent as tool
    layout_agent_as_tool,  # Layout agent as tool
    simulation_agent_as_tool,  # Simulation agent as tool
    report_agent_as_tool,  # Report agent as tool
    generate_project_id,
    load_project_data,
    get_latest_images,
    validate_layout_quality,
    get_project_status,
    analyze_simulation_results,
    load_layout_image
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
    ),
    additional_request_fields={
        "thinking": {
            "type": "enabled",
            "budget_tokens": 4096  # Minimum of 1,024
        }
    }
)

callback_handler = PrintingCallbackHandler()
if disable_callback_handler:
    callback_handler = None

agent = Agent(
    callback_handler=callback_handler,
    tool_executor=SequentialToolExecutor(),
    tools=tools,
    model=bedrock_model,
    system_prompt=DEVELOPMENT_AGENT_SYSTEM_PROMPT
)

logger.info("Agent initialized successfully")


@app.entrypoint
async def agent_invocation(payload):
    """
    Handler for agent invocation
    """
    user_message = payload.get(
        "prompt", "No prompt found in input, please guide customer to create a json payload with prompt key")

    try:
        stream = agent.stream_async(user_message)  # type: ignore
        async for event in stream:
            yield event
    except Exception as e:
        yield {"error": f"Error processing request: {str(e)}"}

if __name__ == "__main__":
    app.run()
