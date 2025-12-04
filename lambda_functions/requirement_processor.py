"""
Requirement Processor Lambda Function
Handles individual security requirement validation with retry logic
"""
import json
import boto3
import time
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Process a single security requirement through the test-validate-refine loop
    
    Expected input:
    {
        "requirement": {...},
        "session_id": "string",
        "service_name": "EC2",
        "environment": "sandbox",
        "test_region": "us-east-1",
        "requirement_index": 0
    }
    """
    
    try:
        requirement = event['requirement']
        session_id = event['session_id']
        service_name = event['service_name']
        requirement_index = event['requirement_index']
        
        logger.info(f"Processing requirement: {requirement.get('description', 'N/A')}")
        
        # Initialize clients
        lambda_client = boto3.client('lambda', region_name=event.get('test_region', 'us-east-1'))
        
        # Maximum retry attempts for refinement
        max_attempts = 3
        current_attempt = 1
        
        while current_attempt <= max_attempts:
            logger.info(f"Attempt {current_attempt} for requirement {requirement_index}")
            
            # Step 1: Deploy test resources
            resource_deployment_result = deploy_test_resources(
                lambda_client, requirement, session_id, service_name, requirement_index
            )
            
            if not resource_deployment_result.get('success'):
                logger.error(f"Failed to deploy resources: {resource_deployment_result.get('error')}")
                return create_failed_response(requirement, resource_deployment_result.get('error'))
            
            resource_ids = resource_deployment_result.get('resource_ids', {})
            
            # Step 2: Run validation tests
            validation_result = run_validation_tests(
                lambda_client, requirement, resource_ids, session_id
            )
            
            if validation_result.get('success'):
                # Test passed - clean up and return success
                cleanup_test_resources(lambda_client, resource_ids, session_id)
                
                requirement['validation_status'] = 'VALIDATED'
                requirement['validation_details'] = validation_result.get('details', {})
                requirement['test_attempts'] = current_attempt
                requirement['validation_timestamp'] = datetime.now().isoformat()
                
                return {
                    'statusCode': 200,
                    'body': requirement
                }
            
            # Test failed - try to refine configuration
            if current_attempt < max_attempts:
                logger.info(f"Test failed, attempting refinement. Attempt {current_attempt}/{max_attempts}")
                
                refinement_result = refine_configuration(
                    lambda_client, requirement, validation_result, current_attempt
                )
                
                if refinement_result.get('success'):
                    # Update requirement with refined configuration
                    requirement['configuration'] = refinement_result.get('refined_config')
                    requirement['refinement_notes'] = refinement_result.get('notes', [])
                else:
                    logger.error(f"Configuration refinement failed: {refinement_result.get('error')}")
                    break
            
            # Clean up resources before retry
            cleanup_test_resources(lambda_client, resource_ids, session_id)
            current_attempt += 1
            
            # Brief pause between attempts
            time.sleep(2)
        
        # All attempts exhausted - return failure
        requirement['validation_status'] = 'FAILED'
        requirement['validation_error'] = validation_result.get('error', 'Maximum retry attempts exceeded')
        requirement['test_attempts'] = max_attempts
        requirement['last_test_details'] = validation_result.get('details', {})
        
        return {
            'statusCode': 200,
            'body': requirement
        }
        
    except Exception as e:
        logger.error(f"Error in requirement processor: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e)
        }

def deploy_test_resources(lambda_client, requirement, session_id, service_name, req_index):
    """Deploy test resources based on the requirement"""
    
    payload = {
        'requirement': requirement,
        'session_id': session_id,
        'service_name': service_name,
        'requirement_index': req_index
    }
    
    try:
        # Choose appropriate resource manager based on service
        if service_name.upper() == 'EC2':
            function_name = 'ec2_resource_manager'
        elif service_name.upper() == 'S3':
            function_name = 's3_resource_manager'
        else:
            # Default to EC2 for now
            function_name = 'ec2_resource_manager'
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps({
                'action': 'deploy',
                **payload
            })
        )
        
        result = json.loads(response['Payload'].read())
        return result
        
    except Exception as e:
        logger.error(f"Error deploying resources: {str(e)}")
        return {'success': False, 'error': str(e)}

def run_validation_tests(lambda_client, requirement, resource_ids, session_id):
    """Run validation tests for the requirement"""
    
    try:
        # Determine which validator to use based on requirement objective
        objective = requirement.get('objective', '').lower()
        
        if 'metadata' in requirement.get('description', '').lower():
            validator_function = 'imds_validator'
        elif 'network' in objective or 'access control' in objective:
            validator_function = 'network_validator'
        elif 'encryption' in objective:
            validator_function = 'encryption_validator'
        else:
            # Default comprehensive validator
            validator_function = 'access_control_validator'
        
        payload = {
            'requirement': requirement,
            'resource_ids': resource_ids,
            'session_id': session_id
        }
        
        response = lambda_client.invoke(
            FunctionName=validator_function,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        return result
        
    except Exception as e:
        logger.error(f"Error running validation: {str(e)}")
        return {'success': False, 'error': str(e)}

def refine_configuration(lambda_client, requirement, validation_result, attempt):
    """Refine the configuration based on test failure"""
    
    try:
        payload = {
            'requirement': requirement,
            'validation_result': validation_result,
            'attempt': attempt
        }
        
        response = lambda_client.invoke(
            FunctionName='config_refiner',
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        return result
        
    except Exception as e:
        logger.error(f"Error refining configuration: {str(e)}")
        return {'success': False, 'error': str(e)}

def cleanup_test_resources(lambda_client, resource_ids, session_id):
    """Clean up test resources"""
    
    try:
        payload = {
            'resource_ids': resource_ids,
            'session_id': session_id,
            'action': 'cleanup'
        }
        
        lambda_client.invoke(
            FunctionName='resource_cleanup',
            InvocationType='Event',  # Async cleanup
            Payload=json.dumps(payload)
        )
        
    except Exception as e:
        logger.error(f"Error triggering cleanup: {str(e)}")

def create_failed_response(requirement, error_message):
    """Create a standardized failed response"""
    
    requirement['validation_status'] = 'FAILED'
    requirement['validation_error'] = error_message
    requirement['validation_timestamp'] = datetime.now().isoformat()
    
    return {
        'statusCode': 200,
        'body': requirement
    }
