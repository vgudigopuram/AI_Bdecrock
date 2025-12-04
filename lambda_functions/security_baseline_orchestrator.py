"""
Main Orchestrator Lambda Function
Handles the entry point for the security baseline generation system
"""
import json
import boto3
from datetime import datetime
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Main orchestrator function that coordinates the entire security baseline process
    
    Expected input:
    {
        "service_name": "EC2",
        "environment": "sandbox",
        "test_region": "us-east-1"
    }
    """
    
    try:
        # Extract input parameters
        service_name = event.get('service_name', 'EC2')
        environment = event.get('environment', 'sandbox')
        test_region = event.get('test_region', 'us-east-1')
        
        session_id = f"{service_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Starting security baseline generation for {service_name} - Session: {session_id}")
        
        # Initialize AWS clients
        bedrock_runtime = boto3.client('bedrock-runtime', region_name=test_region)
        lambda_client = boto3.client('lambda', region_name=test_region)
        
        # Step 1: Generate security requirements using Bedrock
        requirements_response = invoke_bedrock_for_requirements(
            bedrock_runtime, service_name, session_id
        )
        
        if not requirements_response.get('requirements'):
            raise Exception("Failed to generate security requirements")
        
        requirements = requirements_response['requirements']
        logger.info(f"Generated {len(requirements)} security requirements")
        
        # Step 2: Process each requirement through validation
        validated_requirements = []
        
        for req_index, requirement in enumerate(requirements):
            logger.info(f"Processing requirement {req_index + 1}: {requirement.get('description', 'N/A')}")
            
            # Invoke requirement processor
            processor_payload = {
                'requirement': requirement,
                'session_id': session_id,
                'service_name': service_name,
                'environment': environment,
                'test_region': test_region,
                'requirement_index': req_index
            }
            
            processor_response = lambda_client.invoke(
                FunctionName='requirement_processor',
                InvocationType='RequestResponse',
                Payload=json.dumps(processor_payload)
            )
            
            result = json.loads(processor_response['Payload'].read())
            
            if result.get('statusCode') == 200:
                validated_requirements.append(result['body'])
            else:
                logger.error(f"Failed to process requirement {req_index + 1}: {result.get('error')}")
                # Add as failed requirement
                requirement['validation_status'] = 'FAILED'
                requirement['validation_error'] = result.get('error', 'Unknown error')
                validated_requirements.append(requirement)
        
        # Step 3: Generate final report
        final_report = generate_final_report(service_name, session_id, validated_requirements)
        
        # Step 4: Trigger cleanup of any remaining resources
        cleanup_payload = {
            'session_id': session_id,
            'environment': environment
        }
        
        lambda_client.invoke(
            FunctionName='resource_cleanup',
            InvocationType='Event',  # Async cleanup
            Payload=json.dumps(cleanup_payload)
        )
        
        return {
            'statusCode': 200,
            'body': {
                'session_id': session_id,
                'service_name': service_name,
                'total_requirements': len(requirements),
                'validated_requirements': len([r for r in validated_requirements if r.get('validation_status') == 'VALIDATED']),
                'failed_requirements': len([r for r in validated_requirements if r.get('validation_status') == 'FAILED']),
                'report': final_report,
                'requirements_details': validated_requirements
            }
        }
        
    except Exception as e:
        logger.error(f"Error in orchestrator: {str(e)}")
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }

def invoke_bedrock_for_requirements(bedrock_runtime, service_name, session_id):
    """Generate security requirements using Bedrock foundation model"""
    
    prompt = f"""
    You are a cloud security expert. Generate comprehensive security baseline requirements for AWS {service_name}.
    
    For each requirement, provide:
    1. objective: A category like "Access Control", "Encryption", "Network Security"
    2. description: Clear description of what must be configured
    3. configuration: Exact AWS configuration in JSON format
    4. test_method: How to validate this requirement
    5. priority: HIGH, MEDIUM, or LOW
    
    Focus on critical security controls. Provide 5-8 requirements.
    
    Return your response as a JSON object with a "requirements" array.
    
    Example format:
    {{
        "requirements": [
            {{
                "objective": "Access Control",
                "description": "Instance Metadata Service v1 must be disabled",
                "configuration": {{
                    "MetadataOptions": {{
                        "HttpTokens": "required",
                        "HttpEndpoint": "enabled"
                    }}
                }},
                "test_method": "Attempt to access IMDSv1 endpoint without token",
                "priority": "HIGH"
            }}
        ]
    }}
    """
    
    try:
        response = bedrock_runtime.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 2000,
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            })
        )
        
        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']
        
        # Parse JSON from the response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            requirements_data = json.loads(json_match.group())
            return requirements_data
        else:
            raise Exception("Could not parse JSON from Bedrock response")
            
    except Exception as e:
        logger.error(f"Error invoking Bedrock: {str(e)}")
        return {'requirements': []}

def generate_final_report(service_name, session_id, requirements):
    """Generate a comprehensive final report"""
    
    validated_count = len([r for r in requirements if r.get('validation_status') == 'VALIDATED'])
    failed_count = len([r for r in requirements if r.get('validation_status') == 'FAILED'])
    
    report = {
        'session_id': session_id,
        'service_name': service_name,
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_requirements': len(requirements),
            'validated': validated_count,
            'failed': failed_count,
            'success_rate': f"{(validated_count/len(requirements)*100):.1f}%" if requirements else "0%"
        },
        'recommendations': [],
        'next_steps': []
    }
    
    # Add recommendations based on results
    if failed_count > 0:
        report['recommendations'].append(f"Review and manually validate {failed_count} failed requirements")
    
    if validated_count > 0:
        report['recommendations'].append(f"Deploy {validated_count} validated configurations to production")
    
    report['next_steps'].append("Review validation logs for detailed test results")
    report['next_steps'].append("Consider implementing validated configurations in your infrastructure")
    
    return report
