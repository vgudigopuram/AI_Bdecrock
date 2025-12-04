"""
Example usage script for the Security Baseline Automation system
"""
import json
import boto3
import time
from datetime import datetime

def test_security_baseline_system():
    """Test the complete security baseline system"""
    
    # Initialize Lambda client
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print("=== Security Baseline Automation Test ===")
    print(f"Started at: {datetime.now()}")
    
    # Test payload
    test_payload = {
        "service_name": "EC2",
        "environment": "sandbox",
        "test_region": "us-east-1"
    }
    
    print(f"\nTest Input: {json.dumps(test_payload, indent=2)}")
    
    try:
        # Invoke the main orchestrator
        print("\n🚀 Invoking Security Baseline Orchestrator...")
        
        response = lambda_client.invoke(
            FunctionName='security-baseline-orchestrator',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        print(f"\n📊 Response Status Code: {response_payload.get('statusCode')}")
        
        if response_payload.get('statusCode') == 200:
            result = response_payload['body']
            
            print(f"\n✅ SUCCESS! Session ID: {result.get('session_id')}")
            print(f"Service: {result.get('service_name')}")
            print(f"Total Requirements: {result.get('total_requirements')}")
            print(f"Validated: {result.get('validated_requirements')}")
            print(f"Failed: {result.get('failed_requirements')}")
            
            # Display summary
            report = result.get('report', {})
            if report:
                summary = report.get('summary', {})
                print(f"\n📈 Success Rate: {summary.get('success_rate', 'N/A')}")
                
                recommendations = report.get('recommendations', [])
                if recommendations:
                    print("\n💡 Recommendations:")
                    for rec in recommendations:
                        print(f"  • {rec}")
            
            # Display detailed requirements
            requirements_details = result.get('requirements_details', [])
            if requirements_details:
                print(f"\n📋 Detailed Requirements ({len(requirements_details)}):")
                for i, req in enumerate(requirements_details, 1):
                    status = req.get('validation_status', 'UNKNOWN')
                    description = req.get('description', 'No description')
                    objective = req.get('objective', 'N/A')
                    
                    status_emoji = "✅" if status == "VALIDATED" else "❌"
                    print(f"  {i}. {status_emoji} [{objective}] {description}")
                    
                    if status == "VALIDATED":
                        attempts = req.get('test_attempts', 1)
                        if attempts > 1:
                            print(f"     (Validated after {attempts} attempts)")
                    elif status == "FAILED":
                        error = req.get('validation_error', 'Unknown error')
                        print(f"     Error: {error}")
            
            print(f"\n🎯 Test completed successfully!")
            
        else:
            error = response_payload.get('body', {}).get('error', 'Unknown error')
            print(f"\n❌ FAILED: {error}")
            
    except Exception as e:
        print(f"\n💥 ERROR: {str(e)}")
    
    print(f"\nCompleted at: {datetime.now()}")

def test_individual_functions():
    """Test individual Lambda functions"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print("\n=== Testing Individual Functions ===")
    
    # Test EC2 Resource Manager
    print("\n🔧 Testing EC2 Resource Manager...")
    ec2_test_payload = {
        "action": "deploy",
        "requirement": {
            "objective": "Access Control",
            "description": "Instance Metadata Service v1 must be disabled",
            "configuration": {
                "MetadataOptions": {
                    "HttpTokens": "required",
                    "HttpEndpoint": "enabled"
                }
            }
        },
        "session_id": f"test-{int(time.time())}",
        "service_name": "EC2",
        "requirement_index": 0
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='ec2-resource-manager',
            InvocationType='RequestResponse',
            Payload=json.dumps(ec2_test_payload)
        )
        
        result = json.loads(response['Payload'].read())
        if result.get('success'):
            print("  ✅ EC2 Resource Manager working correctly")
            
            # Test cleanup
            cleanup_payload = {
                "action": "cleanup",
                "resource_ids": result.get('resource_ids', {}),
                "session_id": ec2_test_payload['session_id']
            }
            
            lambda_client.invoke(
                FunctionName='resource-cleanup',
                InvocationType='Event',  # Async cleanup
                Payload=json.dumps(cleanup_payload)
            )
            print("  🧹 Cleanup initiated")
            
        else:
            print(f"  ❌ EC2 Resource Manager failed: {result.get('error')}")
            
    except Exception as e:
        print(f"  💥 Error testing EC2 Resource Manager: {str(e)}")

if __name__ == "__main__":
    # Run the complete system test
    test_security_baseline_system()
    
    # Uncomment to test individual functions
    # test_individual_functions()
