"""
EC2 Resource Manager Lambda Function
Handles EC2 instance creation, configuration, and cleanup for security testing
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
    Manage EC2 resources for security baseline testing
    
    Expected input:
    {
        "action": "deploy" | "cleanup",
        "requirement": {...},
        "session_id": "string",
        "service_name": "EC2",
        "requirement_index": 0
    }
    """
    
    try:
        action = event.get('action', 'deploy')
        session_id = event.get('session_id')
        
        if action == 'deploy':
            return deploy_ec2_resources(event)
        elif action == 'cleanup':
            return cleanup_ec2_resources(event)
        else:
            return {'success': False, 'error': f'Unknown action: {action}'}
            
    except Exception as e:
        logger.error(f"Error in EC2 resource manager: {str(e)}")
        return {'success': False, 'error': str(e)}

def deploy_ec2_resources(event):
    """Deploy EC2 instance with specified security configuration"""
    
    requirement = event['requirement']
    session_id = event['session_id']
    req_index = event['requirement_index']
    
    # Initialize AWS clients
    ec2 = boto3.client('ec2')
    
    try:
        # Create unique names/tags for this test
        instance_name = f"security-test-{session_id}-{req_index}"
        vpc_name = f"test-vpc-{session_id}"
        sg_name = f"test-sg-{session_id}-{req_index}"
        
        # Step 1: Create or get VPC for isolated testing
        vpc_id = create_test_vpc(ec2, vpc_name, session_id)
        if not vpc_id:
            raise Exception("Failed to create test VPC")
        
        # Step 2: Create security group
        sg_id = create_test_security_group(ec2, sg_name, vpc_id, session_id)
        if not sg_id:
            raise Exception("Failed to create security group")
        
        # Step 3: Get subnet in the VPC
        subnet_id = get_test_subnet(ec2, vpc_id, session_id)
        if not subnet_id:
            raise Exception("Failed to get test subnet")
        
        # Step 4: Create EC2 instance with security configuration
        instance_id = create_test_instance(
            ec2, requirement, instance_name, subnet_id, sg_id, session_id
        )
        
        if not instance_id:
            raise Exception("Failed to create test instance")
        
        # Wait for instance to be running
        wait_for_instance_running(ec2, instance_id)
        
        # Get instance details
        instance_details = get_instance_details(ec2, instance_id)
        
        resource_ids = {
            'instance_id': instance_id,
            'vpc_id': vpc_id,
            'security_group_id': sg_id,
            'subnet_id': subnet_id,
            'instance_details': instance_details
        }
        
        logger.info(f"Successfully deployed EC2 resources: {instance_id}")
        
        return {
            'success': True,
            'resource_ids': resource_ids,
            'message': f'EC2 instance {instance_id} created successfully'
        }
        
    except Exception as e:
        logger.error(f"Error deploying EC2 resources: {str(e)}")
        # Attempt cleanup of any created resources
        try:
            cleanup_failed_deployment(ec2, locals())
        except:
            pass
        return {'success': False, 'error': str(e)}

def create_test_vpc(ec2, vpc_name, session_id):
    """Create or reuse a test VPC"""
    
    try:
        # Check if VPC already exists for this session
        vpcs = ec2.describe_vpcs(
            Filters=[
                {'Name': 'tag:Name', 'Values': [vpc_name]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        if vpcs['Vpcs']:
            return vpcs['Vpcs'][0]['VpcId']
        
        # Create new VPC
        vpc_response = ec2.create_vpc(
            CidrBlock='10.0.0.0/16',
            TagSpecifications=[
                {
                    'ResourceType': 'vpc',
                    'Tags': [
                        {'Key': 'Name', 'Value': vpc_name},
                        {'Key': 'SessionId', 'Value': session_id},
                        {'Key': 'Purpose', 'Value': 'SecurityBaseline-Testing'}
                    ]
                }
            ]
        )
        
        vpc_id = vpc_response['Vpc']['VpcId']
        
        # Enable DNS hostnames
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
        
        # Create internet gateway
        igw_response = ec2.create_internet_gateway(
            TagSpecifications=[
                {
                    'ResourceType': 'internet-gateway',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'igw-{session_id}'},
                        {'Key': 'SessionId', 'Value': session_id}
                    ]
                }
            ]
        )
        
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        
        # Create subnet
        subnet_response = ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24',
            TagSpecifications=[
                {
                    'ResourceType': 'subnet',
                    'Tags': [
                        {'Key': 'Name', 'Value': f'subnet-{session_id}'},
                        {'Key': 'SessionId', 'Value': session_id}
                    ]
                }
            ]
        )
        
        # Update route table
        route_tables = ec2.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        
        if route_tables['RouteTables']:
            route_table_id = route_tables['RouteTables'][0]['RouteTableId']
            ec2.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=igw_id
            )
        
        return vpc_id
        
    except Exception as e:
        logger.error(f"Error creating VPC: {str(e)}")
        return None

def create_test_security_group(ec2, sg_name, vpc_id, session_id):
    """Create a security group for testing"""
    
    try:
        sg_response = ec2.create_security_group(
            GroupName=sg_name,
            Description=f'Security group for baseline testing - {session_id}',
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    'ResourceType': 'security-group',
                    'Tags': [
                        {'Key': 'Name', 'Value': sg_name},
                        {'Key': 'SessionId', 'Value': session_id},
                        {'Key': 'Purpose', 'Value': 'SecurityBaseline-Testing'}
                    ]
                }
            ]
        )
        
        sg_id = sg_response['GroupId']
        
        # Add minimal ingress rules (SSH for testing if needed)
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]  # Only from VPC
                }
            ]
        )
        
        return sg_id
        
    except Exception as e:
        logger.error(f"Error creating security group: {str(e)}")
        return None

def get_test_subnet(ec2, vpc_id, session_id):
    """Get subnet for testing"""
    
    try:
        subnets = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        if subnets['Subnets']:
            return subnets['Subnets'][0]['SubnetId']
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting subnet: {str(e)}")
        return None

def create_test_instance(ec2, requirement, instance_name, subnet_id, sg_id, session_id):
    """Create EC2 instance with the specified security configuration"""
    
    try:
        # Base instance configuration
        instance_config = {
            'ImageId': 'ami-0c02fb55956c7d316',  # Amazon Linux 2 AMI (update as needed)
            'InstanceType': 't3.micro',
            'SubnetId': subnet_id,
            'SecurityGroupIds': [sg_id],
            'TagSpecifications': [
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': instance_name},
                        {'Key': 'SessionId', 'Value': session_id},
                        {'Key': 'Purpose', 'Value': 'SecurityBaseline-Testing'}
                    ]
                }
            ]
        }
        
        # Apply security configuration from requirement
        config = requirement.get('configuration', {})
        
        # Handle MetadataOptions (IMDS configuration)
        if 'MetadataOptions' in config:
            instance_config['MetadataOptions'] = config['MetadataOptions']
        
        # Handle public IP assignment
        if 'AssociatePublicIpAddress' in config:
            instance_config['AssociatePublicIpAddress'] = config['AssociatePublicIpAddress']
        else:
            # Default to no public IP for security
            instance_config['AssociatePublicIpAddress'] = False
        
        # Handle EBS encryption
        if 'BlockDeviceMappings' in config:
            instance_config['BlockDeviceMappings'] = config['BlockDeviceMappings']
        elif config.get('Encrypted', False):
            instance_config['BlockDeviceMappings'] = [
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
        
        # Launch instance
        response = ec2.run_instances(
            MinCount=1,
            MaxCount=1,
            **instance_config
        )
        
        instance_id = response['Instances'][0]['InstanceId']
        logger.info(f"Created EC2 instance: {instance_id}")
        
        return instance_id
        
    except Exception as e:
        logger.error(f"Error creating EC2 instance: {str(e)}")
        return None

def wait_for_instance_running(ec2, instance_id, timeout=300):
    """Wait for EC2 instance to be in running state"""
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            state = response['Reservations'][0]['Instances'][0]['State']['Name']
            
            if state == 'running':
                logger.info(f"Instance {instance_id} is now running")
                return True
            elif state in ['terminated', 'stopping', 'stopped']:
                logger.error(f"Instance {instance_id} is in unexpected state: {state}")
                return False
            
            time.sleep(10)
            
        except Exception as e:
            logger.error(f"Error checking instance state: {str(e)}")
            time.sleep(10)
    
    logger.error(f"Timeout waiting for instance {instance_id} to be running")
    return False

def get_instance_details(ec2, instance_id):
    """Get detailed information about the instance"""
    
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        
        return {
            'instance_id': instance_id,
            'state': instance['State']['Name'],
            'private_ip': instance.get('PrivateIpAddress'),
            'public_ip': instance.get('PublicIpAddress'),
            'metadata_options': instance.get('MetadataOptions', {}),
            'security_groups': instance.get('SecurityGroups', []),
            'vpc_id': instance.get('VpcId'),
            'subnet_id': instance.get('SubnetId')
        }
        
    except Exception as e:
        logger.error(f"Error getting instance details: {str(e)}")
        return {}

def cleanup_ec2_resources(event):
    """Clean up EC2 resources"""
    
    resource_ids = event.get('resource_ids', {})
    session_id = event.get('session_id')
    
    ec2 = boto3.client('ec2')
    cleanup_results = []
    
    try:
        # Terminate instance
        if resource_ids.get('instance_id'):
            ec2.terminate_instances(InstanceIds=[resource_ids['instance_id']])
            cleanup_results.append(f"Terminated instance: {resource_ids['instance_id']}")
        
        # Wait a bit for instance to terminate
        time.sleep(30)
        
        # Delete security group
        if resource_ids.get('security_group_id'):
            try:
                ec2.delete_security_group(GroupId=resource_ids['security_group_id'])
                cleanup_results.append(f"Deleted security group: {resource_ids['security_group_id']}")
            except Exception as e:
                logger.warning(f"Could not delete security group: {str(e)}")
        
        # Clean up VPC resources (if no other resources are using them)
        cleanup_vpc_resources(ec2, session_id)
        
        return {
            'success': True,
            'cleanup_results': cleanup_results
        }
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'partial_cleanup': cleanup_results
        }

def cleanup_vpc_resources(ec2, session_id):
    """Clean up VPC and related resources if no longer needed"""
    
    try:
        # Check if there are any running instances in VPCs with this session ID
        vpcs = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:SessionId', 'Values': [session_id]}]
        )
        
        for vpc in vpcs['Vpcs']:
            vpc_id = vpc['VpcId']
            
            # Check for running instances
            instances = ec2.describe_instances(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping']}
                ]
            )
            
            if not any(instances['Reservations']):
                # No running instances, safe to clean up VPC
                delete_vpc_and_resources(ec2, vpc_id, session_id)
                
    except Exception as e:
        logger.error(f"Error cleaning up VPC resources: {str(e)}")

def delete_vpc_and_resources(ec2, vpc_id, session_id):
    """Delete VPC and all associated resources"""
    
    try:
        # Delete internet gateway
        igws = ec2.describe_internet_gateways(
            Filters=[
                {'Name': 'attachment.vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        for igw in igws['InternetGateways']:
            ec2.detach_internet_gateway(
                InternetGatewayId=igw['InternetGatewayId'],
                VpcId=vpc_id
            )
            ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
        
        # Delete subnets
        subnets = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        for subnet in subnets['Subnets']:
            ec2.delete_subnet(SubnetId=subnet['SubnetId'])
        
        # Delete VPC
        ec2.delete_vpc(VpcId=vpc_id)
        
        logger.info(f"Successfully deleted VPC: {vpc_id}")
        
    except Exception as e:
        logger.error(f"Error deleting VPC resources: {str(e)}")

def cleanup_failed_deployment(ec2, local_vars):
    """Clean up resources from a failed deployment"""
    
    try:
        # Clean up any resources that were created
        if 'instance_id' in local_vars and local_vars['instance_id']:
            ec2.terminate_instances(InstanceIds=[local_vars['instance_id']])
        
        if 'sg_id' in local_vars and local_vars['sg_id']:
            time.sleep(10)  # Brief wait
            try:
                ec2.delete_security_group(GroupId=local_vars['sg_id'])
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error during failed deployment cleanup: {str(e)}")
