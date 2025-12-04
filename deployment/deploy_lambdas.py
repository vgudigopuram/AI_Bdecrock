"""
Deployment script for Security Baseline Lambda functions
"""
import boto3
import json
import zipfile
import os
from pathlib import Path

# Lambda function configurations
LAMBDA_FUNCTIONS = {
    'security-baseline-orchestrator': {
        'file': 'security_baseline_orchestrator.py',
        'handler': 'security_baseline_orchestrator.lambda_handler',
        'timeout': 900,
        'memory': 512,
        'description': 'Main orchestrator for security baseline generation'
    },
    'requirement-processor': {
        'file': 'requirement_processor.py',
        'handler': 'requirement_processor.lambda_handler',
        'timeout': 300,
        'memory': 256,
        'description': 'Processes individual security requirements'
    },
    'ec2-resource-manager': {
        'file': 'ec2_resource_manager.py',
        'handler': 'ec2_resource_manager.lambda_handler',
        'timeout': 600,
        'memory': 256,
        'description': 'Manages EC2 resources for security testing'
    },
    'imds-validator': {
        'file': 'imds_validator.py',
        'handler': 'imds_validator.lambda_handler',
        'timeout': 300,
        'memory': 256,
        'description': 'Validates IMDS configuration'
    },
    'config-refiner': {
        'file': 'config_refiner.py',
        'handler': 'config_refiner.lambda_handler',
        'timeout': 300,
        'memory': 256,
        'description': 'Refines security configurations based on test failures'
    },
    'resource-cleanup': {
        'file': 'resource_cleanup.py',
        'handler': 'resource_cleanup.lambda_handler',
        'timeout': 900,
        'memory': 256,
        'description': 'Cleans up test resources'
    }
}

def create_lambda_zip(function_file):
    """Create a zip file for Lambda deployment"""
    zip_path = f"/tmp/{function_file.replace('.py', '')}.zip"
    
    with zipfile.ZipFile(zip_path, 'w') as zip_file:
        zip_file.write(f"lambda_functions/{function_file}", function_file)
    
    return zip_path

def create_lambda_execution_role(iam_client, role_name):
    """Create IAM role for Lambda execution"""
    
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        role_response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description='Role for Security Baseline Lambda functions'
        )
        
        # Attach basic Lambda execution policy
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        
        # Create and attach custom policy for AWS resource management
        custom_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "ec2:*",
                        "iam:PassRole",
                        "iam:CreateRole",
                        "iam:DeleteRole",
                        "iam:AttachRolePolicy",
                        "iam:DetachRolePolicy",
                        "iam:ListAttachedRolePolicies",
                        "iam:ListRolePolicies",
                        "iam:DeleteRolePolicy",
                        "iam:CreateInstanceProfile",
                        "iam:DeleteInstanceProfile",
                        "iam:AddRoleToInstanceProfile",
                        "iam:RemoveRoleFromInstanceProfile",
                        "iam:ListInstanceProfilesForRole",
                        "s3:*",
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                        "lambda:InvokeFunction",
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "*"
                }
            ]
        }
        
        iam_client.create_policy(
            PolicyName=f'{role_name}-CustomPolicy',
            PolicyDocument=json.dumps(custom_policy),
            Description='Custom policy for Security Baseline Lambda functions'
        )
        
        # Get account ID for policy ARN
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn=f'arn:aws:iam::{account_id}:policy/{role_name}-CustomPolicy'
        )
        
        return role_response['Role']['Arn']
        
    except iam_client.exceptions.EntityAlreadyExistsException:
        # Role already exists, get ARN
        role = iam_client.get_role(RoleName=role_name)
        return role['Role']['Arn']

def deploy_lambda_function(lambda_client, function_name, config, role_arn):
    """Deploy a Lambda function"""
    
    zip_path = create_lambda_zip(config['file'])
    
    with open(zip_path, 'rb') as zip_file:
        zip_content = zip_file.read()
    
    try:
        # Try to update existing function
        lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_content
        )
        
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Handler=config['handler'],
            Runtime='python3.9',
            Timeout=config['timeout'],
            MemorySize=config['memory'],
            Description=config['description']
        )
        
        print(f"Updated existing Lambda function: {function_name}")
        
    except lambda_client.exceptions.ResourceNotFoundException:
        # Function doesn't exist, create it
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.9',
            Role=role_arn,
            Handler=config['handler'],
            Code={'ZipFile': zip_content},
            Description=config['description'],
            Timeout=config['timeout'],
            MemorySize=config['memory'],
            Environment={
                'Variables': {
                    'LOG_LEVEL': 'INFO'
                }
            }
        )
        
        print(f"Created new Lambda function: {function_name}")
    
    # Clean up zip file
    os.remove(zip_path)

def main():
    """Main deployment function"""
    
    print("Starting Security Baseline Lambda deployment...")
    
    # Initialize AWS clients
    lambda_client = boto3.client('lambda')
    iam_client = boto3.client('iam')
    
    # Create IAM role
    role_name = 'SecurityBaselineLambdaRole'
    role_arn = create_lambda_execution_role(iam_client, role_name)
    print(f"IAM role ready: {role_arn}")
    
    # Wait a bit for role to propagate
    import time
    time.sleep(10)
    
    # Deploy each Lambda function
    for function_name, config in LAMBDA_FUNCTIONS.items():
        try:
            deploy_lambda_function(lambda_client, function_name, config, role_arn)
        except Exception as e:
            print(f"Error deploying {function_name}: {str(e)}")
    
    print("Deployment completed!")
    
    # Print function ARNs for reference
    print("\nDeployed Lambda Functions:")
    for function_name in LAMBDA_FUNCTIONS.keys():
        try:
            response = lambda_client.get_function(FunctionName=function_name)
            print(f"  {function_name}: {response['Configuration']['FunctionArn']}")
        except Exception as e:
            print(f"  {function_name}: Error getting ARN - {str(e)}")

if __name__ == "__main__":
    main()
