from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import boto3
import json
from projects_db import PROJECTS_DB

import os
import asyncio
import logging
from botocore.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# AWS clients
REGION = os.getenv('AWS_DEFAULT_REGION', 'us-west-2')
s3_client = boto3.client('s3', region_name=REGION)
ssm_client = boto3.client('ssm', region_name=REGION)
agentcore_client = boto3.client(
    'bedrock-agentcore',
    region_name=REGION,
    config=Config(read_timeout=900)
)

# Configuration


def get_ssm_parameter(param_name: str) -> str:
    try:
        response = ssm_client.get_parameter(
            Name=param_name,
            WithDecryption=False
        )
        logger.info(f"Retrieved SSM parameter: {param_name}")
        return response['Parameter']['Value']
    except Exception as e:
        logger.error(f"Error getting SSM parameter {param_name}: {e}")
        return ''


S3_BUCKET_NAME = get_ssm_parameter('/wind-farm-assistant/s3-bucket-name')

# S3 Asset Management


async def get_project_assets(project_id: str) -> dict:
    if not S3_BUCKET_NAME:
        logger.error("S3 bucket name not configured")
        return {'assets': [], 'geojson_files': [], 'total_count': 0}

    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=f"{project_id}/"
        )

        assets = []
        geojson_files = []

        for obj in response.get('Contents', []):
            key = obj['Key']
            parts = key.split('/')
            if len(parts) < 2:
                continue

            filename = parts[-1]

            if key.endswith(('.png', '.geojson', '.pdf', '.html')):
                assets.append({
                    'path': '/'.join(parts[1:]),
                    'size': obj['Size'],
                    'modified': obj['LastModified'].isoformat()
                })

                if key.endswith('.geojson'):
                    geojson_files.append(filename)

        return {
            'assets': assets,
            'geojson_files': geojson_files,
            'total_count': len(assets)
        }
    except Exception as e:
        logger.error(f"Error getting assets for project {project_id}: {e}")
        return {'assets': [], 'geojson_files': [], 'total_count': 0}


def process_sub_agent_events(event: dict, current_type_state: dict = {}) -> str:
    if current_type_state is None:
        current_type_state = {'current_type': None}

    current_buffer = ''

    if not isinstance(event, dict):
        return current_buffer

    # Check for tool use start
    if 'event' in event and 'contentBlockStart' in event['event']:
        start_block = event['event']['contentBlockStart'].get('start', {})
        if 'toolUse' in start_block:
            tool_info = start_block['toolUse']
            tool_name = tool_info.get('name', 'unknown')
            current_buffer = f"\n\n🔧 ToolUse: {tool_name} -> Input: "
            current_type_state['current_type'] = "toolUse"
    # Check for metadata (end of section)
    elif 'event' in event and 'metadata' in event['event']:
        current_buffer = "\n"
        current_type_state['current_type'] = ""
    elif 'event' in event and 'contentBlockDelta' in event['event']:
        delta = event['event']['contentBlockDelta'].get('delta', {})

        new_type = ""
        if 'text' in delta:
            new_type = "text"
        elif 'reasoningContent' in delta:
            new_type = "reasoning"
        elif 'toolUse' in delta:
            new_type = "toolUse"

        if new_type != current_type_state['current_type']:
            if new_type == "text":
                current_buffer = "\n\n💬 Response: \n\n"
            elif new_type == "reasoning":
                current_buffer = "\n\n🧠 Reasoning: \n\n"
            else:
                current_buffer = "\n"
            current_type_state['current_type'] = new_type

        if 'text' in delta:
            current_buffer += delta['text']
        elif 'reasoningContent' in delta and 'text' in delta['reasoningContent']:
            current_buffer += delta['reasoningContent']['text']
        elif 'toolUse' in delta and 'input' in delta['toolUse']:
            current_buffer += delta['toolUse']['input']

    return current_buffer


async def generate_response(message: str, project_id: str = ''):
    """Stream response from AgentCore deployed agent"""

    # Get AgentCore runtime ARN from SSM parameter
    agentcore_runtime_arn = get_ssm_parameter(
        '/wind-farm-assistant/agentcore-runtime-arn')
    if not agentcore_runtime_arn:  # Return an error if AgentCore runtime ARN is not configured
        error_msg = "AgentCore runtime ARN not configured in SSM parameter /wind-farm-assistant/agentcore-runtime-arn"
        logger.error(error_msg)
        yield json.dumps({"content": error_msg, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
        return

    try:
        # Update prompt to include project_id
        prompt = f'{message}. Use project_id {project_id}'

        # Invoke agentcore with boto3 client
        boto3_response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=agentcore_runtime_arn,
            qualifier="DEFAULT",
            payload=json.dumps({"prompt": prompt})
        )

        # Process streaming response
        if "text/event-stream" in boto3_response.get("contentType", ""):
            current_buffer = ""
            current_type = ""

            try:
                streaming_body = boto3_response["response"]

                for line in streaming_body.iter_lines(chunk_size=1024):
                    if line:
                        line_decoded = line.decode("utf-8")
                        if line_decoded.startswith("data: "):
                            line_json = line_decoded[6:]
                            try:
                                # Handle string-wrapped JSON
                                if line_json.startswith('"{'):
                                    line_json = line_json.strip(
                                        '"').replace("'", '"')

                                data = json.loads(line_json)

                                # Check for error responses
                                if 'error' in data:
                                    error_msg = f"AgentCore Error: {data['error']}"
                                    yield json.dumps({"content": error_msg, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                    return

                                # Skip init/start events
                                if any(key in data for key in ['init_event_loop', 'start', 'start_event_loop']):
                                    continue

                                # Check for tool use start
                                if 'event' in data and 'contentBlockStart' in data['event']:
                                    if 'toolUse' in data['event']['contentBlockStart']['start']:
                                        tool_info = data['event']['contentBlockStart']['start']['toolUse']
                                        if current_buffer:  # Save previous buffer if exists
                                            yield json.dumps({"content": current_buffer, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                        current_buffer = f"\n\n🔧 ToolUse: {tool_info['name']} -> Input: "
                                        current_type = "toolUse"
                                        yield json.dumps({"content": current_buffer, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                        current_buffer = ""
                                        continue

                                # Check for metadata (end of section)
                                if 'event' in data and 'metadata' in data['event']:
                                    if current_buffer:
                                        yield json.dumps({"content": current_buffer, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                    current_buffer = ""
                                    current_type = ""
                                    continue

                                # Check for content
                                if 'event' in data and 'contentBlockDelta' in data['event']:
                                    delta = data['event']['contentBlockDelta']['delta']

                                    new_type = ""
                                    if 'text' in delta:
                                        new_type = "text"
                                    elif 'reasoningContent' in delta:
                                        new_type = "reasoning"
                                    elif 'toolUse' in delta:
                                        new_type = "toolUse"

                                    if new_type != current_type:
                                        if current_buffer:
                                            yield json.dumps({"content": current_buffer, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                        if new_type == "text":
                                            section_header = "\n\n💬 Response: \n"
                                            yield json.dumps({"content": section_header, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                        elif new_type == "reasoning":
                                            section_header = "\n\n🧠 Reasoning: \n"
                                            yield json.dumps({"content": section_header, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                        current_buffer = ""
                                        current_type = new_type

                                    if 'text' in delta:
                                        content = delta['text']
                                        yield json.dumps({"content": content, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                    elif 'reasoningContent' in delta and 'text' in delta['reasoningContent']:
                                        content = delta['reasoningContent']['text']
                                        yield json.dumps({"content": content, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"
                                    elif 'toolUse' in delta and 'input' in delta['toolUse']:
                                        content = delta['toolUse']['input']
                                        yield json.dumps({"content": content, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"

                            except json.JSONDecodeError:
                                continue

                        # Small delay at end of each line processing
                        await asyncio.sleep(0.05)

                streaming_body.close()

            except Exception as e:
                logger.error(f"Error processing streaming response: {e}")
                yield json.dumps({"content": f"Error processing response: {str(e)}", "type": "response", "subagent": False, "subagent_name": ""}) + "\n"

    except Exception as e:
        error_msg = f"Error calling AgentCore agent: {str(e)}"
        logger.error(error_msg)
        yield json.dumps({"content": error_msg, "type": "response", "subagent": False, "subagent_name": ""}) + "\n"


@app.post("/chat")
def chat(data: dict):
    """Chat endpoint - no auth required"""
    message = data.get("message", "")
    project_id = str(data.get("project_id"))
    is_first_message = data.get("is_first_message", False)
    logger.info(
        f"Chat request - Project: {project_id}, Message length: {len(message)}, First message: {is_first_message}")

    return StreamingResponse(
        generate_response(message, project_id),
        media_type="application/json",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/projects/{username}")
async def get_projects(username: str):
    """Get projects for a user - no auth required"""
    return PROJECTS_DB.get(username, [])


@app.get("/project/{project_id}/info")
async def get_project_info(project_id: str):
    """Get project information by ID"""
    for username, projects in PROJECTS_DB.items():
        for project in projects:
            if project.get('id') == project_id:
                return JSONResponse(content=project)
    return JSONResponse(content={'error': 'Project not found'}, status_code=404)


@app.get("/projects/{project_id}/assets")
async def get_assets_endpoint(project_id: str):
    assets = await get_project_assets(project_id)
    return JSONResponse(content=assets)


@app.get("/projects/{project_id}/{path:path}")
async def get_asset(project_id: str, path: str):
    if not S3_BUCKET_NAME:
        return JSONResponse(content={'error': 'S3 bucket not configured'}, status_code=500)

    try:
        filename = path.split('/')[-1]

        # If path already includes agent folder, use it directly
        if '/' in path:
            key = f"{project_id}/{path}"
        else:
            # Search for file in S3 by listing all objects with the filename
            try:
                response = s3_client.list_objects_v2(
                    Bucket=S3_BUCKET_NAME, Prefix=f"{project_id}/")
                key = None
                for obj in response.get('Contents', []):
                    if obj['Key'].endswith(f"/{filename}"):
                        key = obj['Key']
                        break
                if not key:
                    return JSONResponse(content={'error': f'File {filename} not found in project {project_id}'}, status_code=404)
            except Exception as e:
                logger.error(f"Error listing S3 objects: {e}")
                return JSONResponse(content={'error': 'Failed to search for file'}, status_code=500)

        try:
            response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
            content = response['Body'].read()
        except Exception as e:
            logger.error(f"Error getting S3 object {key}: {e}")
            return JSONResponse(content={'error': 'Failed to retrieve file'}, status_code=404)

        if filename.endswith('.pdf'):
            return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": "inline"})
        elif filename.endswith('.png'):
            return Response(content=content, media_type="image/png")
        elif filename.endswith('.html'):
            return Response(content=content, media_type="text/html")
        elif filename.endswith('.geojson'):
            try:
                return JSONResponse(content=json.loads(content.decode('utf-8')))
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing GeoJSON: {e}")
                return JSONResponse(content={'error': 'Invalid GeoJSON format'}, status_code=400)
        else:
            return Response(content=content)
    except Exception as e:
        logger.error(f"Unexpected error in get_asset: {e}")
        return JSONResponse(content={'error': 'Internal server error'}, status_code=500)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API running"}

# Serve static files (frontend)
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
