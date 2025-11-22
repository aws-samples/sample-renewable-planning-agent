import os
import boto3
from botocore.exceptions import ClientError, NoRegionError
import tempfile
import shutil
import logging

logger = logging.getLogger(__name__)

def get_s3_config():
    """Get S3 configuration from SSM parameters"""
    try:
        logger.debug("Getting S3 configuration from SSM parameters")
        
        # Set default region if not configured
        if not os.environ.get('AWS_DEFAULT_REGION'):
            os.environ['AWS_DEFAULT_REGION'] = 'us-west-2'
            logger.debug("Set default AWS region to us-west-2")
        
        ssm = boto3.client('ssm')
        logger.debug(f"Created SSM client in region: {ssm.meta.region_name}")
        
        # Get S3 bucket name
        logger.debug("Fetching S3 bucket name parameter")
        bucket_response = ssm.get_parameter(
            Name='/wind-farm-assistant/s3-bucket-name',
            WithDecryption=False
        )
        bucket_name = bucket_response['Parameter']['Value']
        logger.debug(f"Found S3 bucket: {bucket_name}")
        
        # Get S3 usage flag
        logger.debug("Fetching S3 usage flag parameter")
        use_s3_response = ssm.get_parameter(
            Name='/wind-farm-assistant/use-s3-storage',
            WithDecryption=False
        )
        use_s3 = use_s3_response['Parameter']['Value'].lower() == 'true'
        logger.debug(f"S3 storage enabled: {use_s3}")
        
        return {
            'use_s3': use_s3,
            'bucket_name': bucket_name
        }
    except ClientError as e:
        if e.response['Error']['Code'] == 'ParameterNotFound':
            return {'use_s3': False, 'bucket_name': None}
        logger.error(f"SSM ClientError: {e}")
        raise e
    except NoRegionError as e:
        logger.error("AWS region not configured. Set AWS_DEFAULT_REGION environment variable.")
        return {'use_s3': False, 'bucket_name': None}
    except Exception as e:
        logger.error(f"Unexpected error getting S3 config: {e}")
        return {'use_s3': False, 'bucket_name': None}


def upload_to_s3(file_path, bucket_name, s3_key):
    """Upload file to S3 bucket"""
    try:
        logger.debug(f"Uploading {file_path} to s3://{bucket_name}/{s3_key}")
        s3 = boto3.client('s3')
        s3.upload_file(file_path, bucket_name, s3_key)
        logger.debug("S3 upload successful")
        return f"s3://{bucket_name}/{s3_key}"
    except Exception as e:
        logger.error(f"Failed to upload to S3: {str(e)}")
        raise Exception(f"Failed to upload to S3: {str(e)}")


def download_from_s3(bucket_name, s3_key, local_path):
    """Download file from S3 bucket"""
    try:
        logger.debug(f"Downloading s3://{bucket_name}/{s3_key} to {local_path}")
        s3 = boto3.client('s3')
        s3.download_file(bucket_name, s3_key, local_path)
        logger.debug("S3 download successful")
        return local_path
    except Exception as e:
        logger.error(f"Failed to download from S3: {str(e)}")
        raise Exception(f"Failed to download from S3: {str(e)}")


def get_storage_paths(project_id, filename, agent_folder=None):
    """
    Get storage paths based on configuration with agent-specific folders
    
    Args:
        project_id: Project identifier
        filename: Name of the file
        agent_folder: Agent-specific folder (e.g., 'terrain_agent', 'layout_agent')

    Returns:
        dict with storage configuration and paths
    """
    logger.debug(f"Getting storage paths for project={project_id}, file={filename}, agent={agent_folder}")
    s3_config = get_s3_config()
    use_s3_storage = s3_config['use_s3'] and s3_config['bucket_name']
    logger.debug(f"Using {'S3' if use_s3_storage else 'local'} storage")
    
    # Build path with agent folder if provided
    if agent_folder:
        file_path = f"{agent_folder}/{filename}"
        s3_key = f"{project_id}/{agent_folder}/{filename}"
    else:
        file_path = filename
        s3_key = f"{project_id}/{filename}"
    
    if use_s3_storage:
        temp_dir = tempfile.mkdtemp()
        local_path = os.path.join(temp_dir, file_path)
        logger.debug(f"S3 storage: temp_dir={temp_dir}, local_path={local_path}, s3_key={s3_key}")
        
        # Create subdirectories if file_path contains path separators
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        return {
            'use_s3': True,
            'bucket_name': s3_config['bucket_name'],
            'local_path': local_path,
            's3_key': s3_key,
            'temp_dir': temp_dir
        }
    else:
        # Get project root for local storage
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        
        if agent_folder:
            project_dir = os.path.join(project_root, "assets", project_id, agent_folder)
        else:
            project_dir = os.path.join(project_root, "assets", project_id)
        
        local_path = os.path.join(project_dir, filename)
        logger.debug(f"Local storage: project_dir={project_dir}, local_path={local_path}")
        
        # Create subdirectories if filename contains path separators
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        return {
            'use_s3': False,
            'bucket_name': None,
            'local_path': local_path,
            's3_key': None,
            'temp_dir': None
        }


def save_file_with_storage(content, project_id, filename, content_type="text", agent_folder=None):
    """
    Save file using configured storage (S3 or local) with agent-specific folders
    
    Args:
        content: File content (text, bytes, or file path to copy)
        project_id: Project identifier
        filename: Name of the file
        content_type: 'text', 'bytes', or 'file_copy'
        agent_folder: Agent-specific folder (e.g., 'terrain_agent', 'layout_agent')
    
    Returns:
        dict with storage results
    """
    logger.debug(f"Saving file: {filename} for project {project_id} (type: {content_type})")
    storage_config = get_storage_paths(project_id, filename, agent_folder)
    
    # Write content to local path
    logger.debug(f"Writing content to: {storage_config['local_path']}")
    if content_type == "text":
        with open(storage_config['local_path'], 'w') as f:
            f.write(content)
    elif content_type == "bytes":
        with open(storage_config['local_path'], 'wb') as f:
            f.write(content)
    elif content_type == "file_copy":
        shutil.copy2(content, storage_config['local_path'])
    logger.debug("Content written successfully")
    
    # Handle S3 upload if configured
    if storage_config['use_s3']:
        try:
            s3_url = upload_to_s3(
                storage_config['local_path'], 
                storage_config['bucket_name'], 
                storage_config['s3_key']
            )
            
            # Clean up temp files
            shutil.rmtree(storage_config['temp_dir'])
            
            return {
                'storage_type': 's3',
                's3_url': s3_url,
                'filename': filename
            }
        except Exception as e:
            # Clean up temp files on error
            shutil.rmtree(storage_config['temp_dir'], ignore_errors=True)
            raise e
    else:
        return {
            'storage_type': 'local',
            'local_path': storage_config['local_path'],
            'filename': filename
        }


def load_file_from_storage(project_id, filename, agent_folder=None):
    """
    Load file from configured storage (S3 or local) with agent-specific folders
    
    Args:
        project_id: Project identifier
        filename: Name of the file
        agent_folder: Agent-specific folder (e.g., 'terrain_agent', 'layout_agent')

    Returns:
        Local file path where content can be read
    """
    logger.debug(f"Loading file: {filename} for project {project_id} from agent {agent_folder}")
    s3_config = get_s3_config()
    use_s3_storage = s3_config['use_s3'] and s3_config['bucket_name']
    logger.debug(f"Using {'S3' if use_s3_storage else 'local'} storage for loading")
    
    if use_s3_storage:
        temp_dir = tempfile.mkdtemp()
        local_path = os.path.join(temp_dir, filename)
        
        if agent_folder:
            s3_key = f"{project_id}/{agent_folder}/{filename}"
        else:
            s3_key = f"{project_id}/{filename}"
        
        download_from_s3(s3_config['bucket_name'], s3_key, local_path)
        return local_path
    else:
        # Local storage
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        
        if agent_folder:
            local_path = os.path.join(project_root, "assets", project_id, agent_folder, filename)
        else:
            local_path = os.path.join(project_root, "assets", project_id, filename)
        
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"File not found: {local_path}")
        
        logger.debug(f"File found at: {local_path}")
        return local_path