"""
IMDS Validator Lambda Function
Tests Instance Metadata Service configuration for security compliance
"""
import json
import boto3
import requests
import time
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Validate Instance Metadata Service (IMDS) configuration
    
    Expected input:
    {
        "requirement": {...},
        "resource_ids": {...},
        "session_id": "string"
    }
    """
    
    try:
        requirement = event['requirement']
        resource_ids = event['resource_ids']
        session_id = event['session_id']
        
        instance_id = resource_ids.get('instance_id')
        instance_details = resource_ids.get('instance_details', {})
        
        logger.info(f"Validating IMDS configuration for instance: {instance_id}")
        
        # Run IMDS validation tests
        validation_results = run_imds_tests(instance_id, instance_details, requirement)
        
        # Analyze results
        success = analyze_imds_results(validation_results, requirement)
        
        response = {
            'success': success,
            'validation_type': 'IMDS',
            'instance_id': instance_id,
            'test_results': validation_results,
            'timestamp': datetime.now().isoformat()
        }
        
        if success:
            response['details'] = {
                'message': 'IMDS configuration validated successfully',
                'tests_passed': len([r for r in validation_results if r.get('passed')]),
                'total_tests': len(validation_results)
            }
        else:
            response['error'] = 'One or more IMDS tests failed'
            response['failed_tests'] = [r for r in validation_results if not r.get('passed')]
        
        return response
        
    except Exception as e:
        logger.error(f"Error in IMDS validator: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'validation_type': 'IMDS'
        }

def run_imds_tests(instance_id, instance_details, requirement):
    """Run comprehensive IMDS tests"""
    
    test_results = []
    
    # Test 1: Check MetadataOptions configuration
    metadata_config_result = test_metadata_options(instance_id, requirement)
    test_results.append(metadata_config_result)
    
    # Test 2: Test IMDSv1 accessibility (should fail if properly configured)
    imdsv1_access_result = test_imdsv1_access(instance_details)
    test_results.append(imdsv1_access_result)
    
    # Test 3: Test IMDSv2 token requirement
    imdsv2_token_result = test_imdsv2_token_requirement(instance_details)
    test_results.append(imdsv2_token_result)
    
    # Test 4: Test hop limit configuration
    hop_limit_result = test_hop_limit(instance_details)
    test_results.append(hop_limit_result)
    
    return test_results

def test_metadata_options(instance_id, requirement):
    """Test the MetadataOptions configuration directly"""
    
    try:
        ec2 = boto3.client('ec2')
        
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        actual_metadata_options = instance.get('MetadataOptions', {})
        
        # Get expected configuration from requirement
        expected_config = requirement.get('configuration', {}).get('MetadataOptions', {})
        
        # Check each expected setting
        test_result = {
            'test_name': 'MetadataOptions Configuration',
            'test_type': 'configuration_check',
            'expected': expected_config,
            'actual': actual_metadata_options,
            'details': [],
            'passed': True
        }
        
        for key, expected_value in expected_config.items():
            actual_value = actual_metadata_options.get(key)
            
            if actual_value == expected_value:
                test_result['details'].append({
                    'setting': key,
                    'expected': expected_value,
                    'actual': actual_value,
                    'status': 'PASS'
                })
            else:
                test_result['details'].append({
                    'setting': key,
                    'expected': expected_value,
                    'actual': actual_value,
                    'status': 'FAIL'
                })
                test_result['passed'] = False
        
        return test_result
        
    except Exception as e:
        return {
            'test_name': 'MetadataOptions Configuration',
            'test_type': 'configuration_check',
            'passed': False,
            'error': str(e)
        }

def test_imdsv1_access(instance_details):
    """Test if IMDSv1 is properly blocked"""
    
    test_result = {
        'test_name': 'IMDSv1 Access Block',
        'test_type': 'network_test',
        'passed': False,
        'details': {}
    }
    
    try:
        private_ip = instance_details.get('private_ip')
        
        if not private_ip:
            test_result['error'] = 'No private IP available for testing'
            return test_result
        
        # Simulate IMDSv1 request (this would normally be done from within the instance)
        # For this simulation, we'll check the configuration and infer the result
        metadata_options = instance_details.get('metadata_options', {})
        http_tokens = metadata_options.get('HttpTokens', 'optional')
        
        if http_tokens == 'required':
            # If HttpTokens is required, IMDSv1 should be blocked
            test_result['passed'] = True
            test_result['details'] = {
                'message': 'IMDSv1 is properly blocked (HttpTokens: required)',
                'http_tokens': http_tokens,
                'expected_result': 'IMDSv1 requests should fail',
                'actual_result': 'IMDSv1 blocked due to token requirement'
            }
        else:
            # If HttpTokens is optional, IMDSv1 is still accessible
            test_result['passed'] = False
            test_result['details'] = {
                'message': 'IMDSv1 is still accessible (HttpTokens: optional)',
                'http_tokens': http_tokens,
                'expected_result': 'IMDSv1 requests should fail',
                'actual_result': 'IMDSv1 still accessible'
            }
        
        return test_result
        
    except Exception as e:
        test_result['error'] = str(e)
        return test_result

def test_imdsv2_token_requirement(instance_details):
    """Test IMDSv2 token requirement enforcement"""
    
    test_result = {
        'test_name': 'IMDSv2 Token Requirement',
        'test_type': 'security_test',
        'passed': False,
        'details': {}
    }
    
    try:
        metadata_options = instance_details.get('metadata_options', {})
        http_tokens = metadata_options.get('HttpTokens', 'optional')
        http_endpoint = metadata_options.get('HttpEndpoint', 'enabled')
        
        # Check if token is required and endpoint is enabled
        if http_tokens == 'required' and http_endpoint == 'enabled':
            test_result['passed'] = True
            test_result['details'] = {
                'message': 'IMDSv2 token requirement properly configured',
                'http_tokens': http_tokens,
                'http_endpoint': http_endpoint,
                'security_impact': 'Prevents unauthorized metadata access'
            }
        elif http_endpoint == 'disabled':
            test_result['passed'] = True
            test_result['details'] = {
                'message': 'IMDS endpoint completely disabled',
                'http_endpoint': http_endpoint,
                'security_impact': 'Maximum security - no metadata access possible'
            }
        else:
            test_result['passed'] = False
            test_result['details'] = {
                'message': 'IMDSv2 token requirement not properly enforced',
                'http_tokens': http_tokens,
                'http_endpoint': http_endpoint,
                'security_risk': 'Allows unauthorized metadata access'
            }
        
        return test_result
        
    except Exception as e:
        test_result['error'] = str(e)
        return test_result

def test_hop_limit(instance_details):
    """Test the hop limit configuration for additional security"""
    
    test_result = {
        'test_name': 'IMDS Hop Limit',
        'test_type': 'configuration_test',
        'passed': False,
        'details': {}
    }
    
    try:
        metadata_options = instance_details.get('metadata_options', {})
        hop_limit = metadata_options.get('HttpPutResponseHopLimit', 1)  # Default is 1
        
        # Hop limit of 1 is most secure (prevents access from containers/forwarded requests)
        if hop_limit == 1:
            test_result['passed'] = True
            test_result['details'] = {
                'message': 'Hop limit properly configured for maximum security',
                'hop_limit': hop_limit,
                'security_impact': 'Prevents metadata access from containers and forwarded requests'
            }
        else:
            test_result['passed'] = False
            test_result['details'] = {
                'message': f'Hop limit set to {hop_limit}, consider reducing to 1 for better security',
                'hop_limit': hop_limit,
                'recommendation': 'Set HttpPutResponseHopLimit to 1 for maximum security'
            }
        
        return test_result
        
    except Exception as e:
        test_result['error'] = str(e)
        return test_result

def analyze_imds_results(validation_results, requirement):
    """Analyze the IMDS validation results to determine overall success"""
    
    try:
        # Count passed and failed tests
        passed_tests = [r for r in validation_results if r.get('passed', False)]
        failed_tests = [r for r in validation_results if not r.get('passed', False)]
        
        logger.info(f"IMDS validation results: {len(passed_tests)} passed, {len(failed_tests)} failed")
        
        # For IMDS, we need all critical tests to pass
        critical_tests = [
            'MetadataOptions Configuration',
            'IMDSv1 Access Block',
            'IMDSv2 Token Requirement'
        ]
        
        critical_failures = []
        for test in validation_results:
            if test.get('test_name') in critical_tests and not test.get('passed', False):
                critical_failures.append(test.get('test_name'))
        
        if not critical_failures:
            logger.info("All critical IMDS tests passed")
            return True
        else:
            logger.warning(f"Critical IMDS tests failed: {critical_failures}")
            return False
            
    except Exception as e:
        logger.error(f"Error analyzing IMDS results: {str(e)}")
        return False

def simulate_metadata_request(endpoint_url, use_token=False):
    """Simulate a metadata request (for demonstration purposes)"""
    
    try:
        headers = {}
        
        if use_token:
            # In a real scenario, we would first get a token
            # PUT request to http://169.254.169.254/latest/api/token
            # For simulation, we'll assume we have a token
            headers['X-aws-ec2-metadata-token'] = 'simulated-token'
        
        # This is a simulation - in real testing, this would be done from within the EC2 instance
        response = requests.get(
            endpoint_url,
            headers=headers,
            timeout=5
        )
        
        return {
            'status_code': response.status_code,
            'success': response.status_code == 200,
            'response_text': response.text[:100] if response.text else None
        }
        
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': str(e),
            'expected': 'Connection should fail if IMDS is properly secured'
        }
