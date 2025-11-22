from get_wind_conditions import get_wind_conditions

def lambda_handler(event, context):
    """Lambda handler for AgentCore gateway"""
    return get_wind_conditions(**event)
