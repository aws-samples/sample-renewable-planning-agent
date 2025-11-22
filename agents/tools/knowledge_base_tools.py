import os
import boto3
import logging
from typing import Dict, List, Any
from strands import tool

logger = logging.getLogger(__name__)


# Initialize Bedrock client
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name="us-west-2")

@tool
def query_knowledge_base(query: str, knowledge_base_id: str = None, max_results: int = 5) -> Dict[str, Any]:
    """
    Query AWS Bedrock Knowledge Base for relevant information.
    
    Args:
        query (str): The question or search query
        knowledge_base_id (str): Knowledge base ID (optional, uses env var if not provided)
        max_results (int): Maximum number of results to return
        
    Returns:
        Dict containing retrieved knowledge and sources
    """
    try:
        # Use provided KB ID or get from environment
        kb_id = knowledge_base_id or os.getenv('KNOWLEDGE_BASE_ID')
        if not kb_id:
            return {
                'success': False,
                'error': 'No knowledge base ID provided. Set KNOWLEDGE_BASE_ID environment variable.'
            }
        
        logger.info(f"Querying knowledge base {kb_id} with query: {query}")
        
        response = bedrock_agent_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': max_results
                }
            }
        )
        
        # Extract and format results
        results = []
        sources = []
        
        for item in response['retrievalResults']:
            content = item['content']['text']
            source = item.get('location', {}).get('s3Location', {})
            
            results.append(content)
            if source:
                sources.append({
                    'uri': source.get('uri', 'Unknown'),
                    'score': item.get('score', 0)
                })
        
        return {
            'success': True,
            'query': query,
            'results': results,
            'sources': sources,
            'combined_text': "\n\n".join(results),
            'total_results': len(results)
        }
        
    except Exception as e:
        logger.error(f"Error querying knowledge base: {e}")
        return {
            'success': False,
            'error': f"Failed to query knowledge base: {str(e)}"
        }