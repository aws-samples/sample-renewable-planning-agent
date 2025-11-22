"""Shared MCP utilities for remote and local MCP server connections"""
import boto3
import json
import logging
import requests
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("mac_utils")

def get_mcp_config():
    """Get MCP configuration from AWS SSM and Secrets Manager"""
    try:
        ssm = boto3.client('ssm')
        secrets = boto3.client('secretsmanager')
        
        # Get gateway URL from SSM
        gateway_url = ssm.get_parameter(Name='/nrel-mcp/gateway-url')['Parameter']['Value']
        token_url = ssm.get_parameter(Name='/nrel-mcp/token-url')['Parameter']['Value']
        
        # Get credentials from Secrets Manager
        secret = secrets.get_secret_value(SecretId='nrel-mcp-credentials')
        creds = json.loads(secret['SecretString'])
        
        return {
            'gateway_url': gateway_url,
            'token_url': token_url,
            'client_id': creds['client_id'],
            'client_secret': creds['client_secret']
        }
    except Exception as e:
        logger.warning(f"Failed to get MCP config from AWS: {e}")
        return None

def fetch_access_token(client_id, client_secret, token_url):
    """Fetch access token for remote MCP server"""
    response = requests.post(
        token_url,
        data=f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}",
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    return response.json()['access_token']

def create_streamable_http_transport(mcp_url: str, access_token: str):
    """Create HTTP transport for remote MCP server"""
    return streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {access_token}"})

def get_full_tools_list(client):
    """List tools with pagination support"""
    more_tools = True
    tools = []
    pagination_token = None
    while more_tools:
        tmp_tools = client.list_tools_sync(pagination_token=pagination_token)
        tools.extend(tmp_tools)
        if tmp_tools.pagination_token is None:
            more_tools = False
        else:
            more_tools = True 
            pagination_token = tmp_tools.pagination_token
    return tools