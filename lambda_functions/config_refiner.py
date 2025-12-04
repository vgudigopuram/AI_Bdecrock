"""
Configuration Refiner Lambda Function
Uses Bedrock to analyze failed tests and refine security configurations
"""
import json
import boto3
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Refine security configuration based on failed validation results
    
    Expected input:
    {
        "requirement": {...},
        "validation_result": {...},
        "attempt": 1
    }
    """
    
    try:
        requirement = event['requirement']
        validation_result = event['validation_result']
        attempt = event.get('attempt', 1)
        
        logger.info(f"Refining configuration for requirement: {requirement.get('description', 'N/A')} - Attempt {attempt}")
        
        # Use Bedrock to analyze the failure and suggest improvements
        refined_config = refine_with_bedrock(requirement, validation_result, attempt)
        
        if refined_config:
            return {
                'success': True,
                'refined_config': refined_config,
                'attempt': attempt,
                'refinement_timestamp': datetime.now().isoformat(),
                'notes': [
                    f"Configuration refined based on test failure analysis - Attempt {attempt}",
                    f"Original validation error: {validation_result.get('error', 'Test validation failed')}"
                ]
            }
        else:
            return {
                'success': False,
                'error': 'Could not generate refined configuration',
                'attempt': attempt
            }
            
    except Exception as e:
        logger.error(f"Error in config refiner: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'attempt': event.get('attempt', 1)
        }

def refine_with_bedrock(requirement, validation_result, attempt):
    """Use Bedrock to analyze failure and refine configuration"""
    
    try:
        bedrock_runtime = boto3.client('bedrock-runtime')
        
        # Create detailed prompt for configuration refinement
        prompt = create_refinement_prompt(requirement, validation_result, attempt)
        
        response = bedrock_runtime.invoke_model(
            modelId='anthropic.claude-3-sonnet-20240229-v1:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 1000,
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
        
        # Extract JSON configuration from response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            refined_config = json.loads(json_match.group())
            logger.info(f"Generated refined configuration: {refined_config}")
            return refined_config
        else:
            logger.error("Could not extract JSON from Bedrock response")
            return None
            
    except Exception as e:
        logger.error(f"Error refining configuration with Bedrock: {str(e)}")
        return None

def create_refinement_prompt(requirement, validation_result, attempt):
    """Create a detailed prompt for Bedrock to refine the configuration"""
    
    failed_tests = validation_result.get('failed_tests', [])
    test_details = validation_result.get('test_results', [])
    
    prompt = f"""
You are an AWS security expert tasked with refining a security configuration that failed validation tests.

ORIGINAL REQUIREMENT:
- Objective: {requirement.get('objective', 'N/A')}
- Description: {requirement.get('description', 'N/A')}
- Current Configuration: {json.dumps(requirement.get('configuration', {}), indent=2)}

VALIDATION FAILURE DETAILS:
- Attempt Number: {attempt}
- Validation Error: {validation_result.get('error', 'N/A')}
- Failed Tests: {json.dumps(failed_tests, indent=2)}

DETAILED TEST RESULTS:
{json.dumps(test_details, indent=2)}

Based on the test failure analysis, please provide a refined AWS configuration that addresses the identified issues.

INSTRUCTIONS:
1. Analyze why the current configuration failed the tests
2. Identify the specific AWS settings that need to be modified
3. Provide a corrected configuration in JSON format
4. Focus on the most restrictive security settings that will pass the validation

For IMDS (Instance Metadata Service) issues:
- If IMDSv1 is still accessible, ensure HttpTokens is set to "required"
- If metadata access is too permissive, consider setting HttpEndpoint to "disabled"
- Verify HttpPutResponseHopLimit is set to 1 for maximum security

For network security issues:
- Ensure security groups have minimal required access
- Check that public IP assignment is disabled if required
- Verify encryption settings are properly configured

Return ONLY the refined configuration as a JSON object, without any explanation text.

Example response format:
{{
    "MetadataOptions": {{
        "HttpTokens": "required",
        "HttpEndpoint": "enabled",
        "HttpPutResponseHopLimit": 1
    }}
}}
"""
    
    return prompt

def fallback_refinement(requirement, validation_result, attempt):
    """Provide fallback refinement logic if Bedrock fails"""
    
    try:
        current_config = requirement.get('configuration', {})
        objective = requirement.get('objective', '').lower()
        description = requirement.get('description', '').lower()
        
        refined_config = current_config.copy()
        
        # IMDS-specific refinements
        if 'metadata' in description or 'imds' in description:
            metadata_options = refined_config.get('MetadataOptions', {})
            
            if attempt == 1:
                # First attempt: Require tokens but keep endpoint enabled
                metadata_options['HttpTokens'] = 'required'
                metadata_options['HttpEndpoint'] = 'enabled'
                metadata_options['HttpPutResponseHopLimit'] = 1
            elif attempt == 2:
                # Second attempt: More restrictive - disable endpoint entirely
                metadata_options['HttpTokens'] = 'required'
                metadata_options['HttpEndpoint'] = 'disabled'
            
            refined_config['MetadataOptions'] = metadata_options
        
        # Network security refinements
        elif 'network' in objective or 'access control' in objective:
            if attempt == 1:
                # Ensure no public IP
                refined_config['AssociatePublicIpAddress'] = False
            elif attempt == 2:
                # Add additional network restrictions
                refined_config['AssociatePublicIpAddress'] = False
                refined_config['EbsOptimized'] = True
        
        # Encryption refinements
        elif 'encryption' in objective:
            if not refined_config.get('BlockDeviceMappings'):
                refined_config['BlockDeviceMappings'] = [
                    {
                        'DeviceName': '/dev/xvda',
                        'Ebs': {
                            'VolumeSize': 8,
                            'VolumeType': 'gp3',
                            'Encrypted': True,
                            'DeleteOnTermination': True
                        }
                    }
                ]
        
        logger.info(f"Generated fallback refined configuration: {refined_config}")
        return refined_config
        
    except Exception as e:
        logger.error(f"Error in fallback refinement: {str(e)}")
        return None
