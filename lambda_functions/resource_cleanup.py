"""
Resource Cleanup Lambda Function
Handles cleanup of all test resources across different AWS services
"""
import json
import boto3
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Clean up test resources based on session ID or specific resource IDs
    
    Expected input:
    {
        "session_id": "string",
        "resource_ids": {...},  # Optional: specific resources to clean up
        "environment": "sandbox",
        "cleanup_type": "session" | "resources"  # Optional
    }
    """
    
    try:
        session_id = event.get('session_id')
        resource_ids = event.get('resource_ids', {})
        cleanup_type = event.get('cleanup_type', 'session')
        
        if not session_id:
            raise ValueError("session_id is required for cleanup")
        
        logger.info(f"Starting cleanup for session: {session_id}, type: {cleanup_type}")
        
        cleanup_results = {}
        
        if cleanup_type == 'resources' and resource_ids:
            # Clean up specific resources
            cleanup_results = cleanup_specific_resources(resource_ids, session_id)
        else:
            # Clean up all resources for the session
            cleanup_results = cleanup_session_resources(session_id)
        
        return {
            'statusCode': 200,
            'body': {
                'session_id': session_id,
                'cleanup_completed': datetime.now().isoformat(),
                'results': cleanup_results
            }
        }
        
    except Exception as e:
        logger.error(f"Error in resource cleanup: {str(e)}")
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }

def cleanup_session_resources(session_id):
    """Clean up all resources associated with a session ID"""
    
    cleanup_results = {
        'ec2_instances': [],
        'security_groups': [],
        'vpcs': [],
        's3_buckets': [],
        'iam_resources': [],
        'errors': []
    }
    
    try:
        # Clean up EC2 resources
        ec2_results = cleanup_ec2_resources_by_session(session_id)
        cleanup_results['ec2_instances'] = ec2_results.get('instances', [])
        cleanup_results['security_groups'] = ec2_results.get('security_groups', [])
        cleanup_results['vpcs'] = ec2_results.get('vpcs', [])
        
        # Clean up S3 resources
        s3_results = cleanup_s3_resources_by_session(session_id)
        cleanup_results['s3_buckets'] = s3_results.get('buckets', [])
        
        # Clean up IAM resources
        iam_results = cleanup_iam_resources_by_session(session_id)
        cleanup_results['iam_resources'] = iam_results.get('resources', [])
        
        # Collect any errors
        for service_result in [ec2_results, s3_results, iam_results]:
            if service_result.get('errors'):
                cleanup_results['errors'].extend(service_result['errors'])
        
        logger.info(f"Session cleanup completed for {session_id}")
        
    except Exception as e:
        logger.error(f"Error during session cleanup: {str(e)}")
        cleanup_results['errors'].append(str(e))
    
    return cleanup_results

def cleanup_specific_resources(resource_ids, session_id):
    """Clean up specific resources identified by their IDs"""
    
    cleanup_results = {
        'cleaned_resources': [],
        'errors': []
    }
    
    try:
        ec2 = boto3.client('ec2')
        
        # Terminate EC2 instances
        if resource_ids.get('instance_id'):
            try:
                ec2.terminate_instances(InstanceIds=[resource_ids['instance_id']])
                cleanup_results['cleaned_resources'].append({
                    'type': 'EC2 Instance',
                    'id': resource_ids['instance_id'],
                    'action': 'terminated'
                })
                logger.info(f"Terminated instance: {resource_ids['instance_id']}")
            except Exception as e:
                cleanup_results['errors'].append(f"Failed to terminate instance {resource_ids['instance_id']}: {str(e)}")
        
        # Wait for instance termination before cleaning up dependent resources
        if resource_ids.get('instance_id'):
            wait_for_instance_termination(ec2, resource_ids['instance_id'])
        
        # Delete security groups
        if resource_ids.get('security_group_id'):
            try:
                ec2.delete_security_group(GroupId=resource_ids['security_group_id'])
                cleanup_results['cleaned_resources'].append({
                    'type': 'Security Group',
                    'id': resource_ids['security_group_id'],
                    'action': 'deleted'
                })
                logger.info(f"Deleted security group: {resource_ids['security_group_id']}")
            except Exception as e:
                cleanup_results['errors'].append(f"Failed to delete security group {resource_ids['security_group_id']}: {str(e)}")
        
        # Clean up VPC if specified
        if resource_ids.get('vpc_id'):
            vpc_cleanup_result = cleanup_vpc_resources(ec2, resource_ids['vpc_id'], session_id)
            if vpc_cleanup_result.get('success'):
                cleanup_results['cleaned_resources'].extend(vpc_cleanup_result.get('resources', []))
            else:
                cleanup_results['errors'].extend(vpc_cleanup_result.get('errors', []))
        
    except Exception as e:
        cleanup_results['errors'].append(str(e))
        logger.error(f"Error cleaning specific resources: {str(e)}")
    
    return cleanup_results

def cleanup_ec2_resources_by_session(session_id):
    """Clean up all EC2 resources tagged with the session ID"""
    
    ec2 = boto3.client('ec2')
    results = {
        'instances': [],
        'security_groups': [],
        'vpcs': [],
        'errors': []
    }
    
    try:
        # Find and terminate instances
        instances_response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:SessionId', 'Values': [session_id]},
                {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping', 'stopped']}
            ]
        )
        
        instance_ids = []
        for reservation in instances_response['Reservations']:
            for instance in reservation['Instances']:
                instance_ids.append(instance['InstanceId'])
        
        if instance_ids:
            ec2.terminate_instances(InstanceIds=instance_ids)
            results['instances'] = [{'id': iid, 'action': 'terminated'} for iid in instance_ids]
            logger.info(f"Terminated {len(instance_ids)} instances")
            
            # Wait for instances to terminate
            for instance_id in instance_ids:
                wait_for_instance_termination(ec2, instance_id)
        
        # Clean up security groups
        sgs_response = ec2.describe_security_groups(
            Filters=[{'Name': 'tag:SessionId', 'Values': [session_id]}]
        )
        
        for sg in sgs_response['SecurityGroups']:
            if sg['GroupName'] != 'default':  # Don't delete default security group
                try:
                    ec2.delete_security_group(GroupId=sg['GroupId'])
                    results['security_groups'].append({'id': sg['GroupId'], 'action': 'deleted'})
                except Exception as e:
                    results['errors'].append(f"Failed to delete security group {sg['GroupId']}: {str(e)}")
        
        # Clean up VPCs
        vpcs_response = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:SessionId', 'Values': [session_id]}]
        )
        
        for vpc in vpcs_response['Vpcs']:
            if not vpc['IsDefault']:  # Don't delete default VPC
                vpc_cleanup = cleanup_vpc_resources(ec2, vpc['VpcId'], session_id)
                if vpc_cleanup.get('success'):
                    results['vpcs'].append({'id': vpc['VpcId'], 'action': 'deleted'})
                else:
                    results['errors'].extend(vpc_cleanup.get('errors', []))
        
    except Exception as e:
        results['errors'].append(str(e))
        logger.error(f"Error cleaning EC2 resources: {str(e)}")
    
    return results

def cleanup_s3_resources_by_session(session_id):
    """Clean up S3 buckets created for testing"""
    
    s3 = boto3.client('s3')
    results = {
        'buckets': [],
        'errors': []
    }
    
    try:
        # List all buckets and check tags
        buckets_response = s3.list_buckets()
        
        for bucket in buckets_response['Buckets']:
            bucket_name = bucket['Name']
            
            # Check if bucket has our session tag
            try:
                tags_response = s3.get_bucket_tagging(Bucket=bucket_name)
                tags = {tag['Key']: tag['Value'] for tag in tags_response['TagSet']}
                
                if tags.get('SessionId') == session_id:
                    # Empty and delete the bucket
                    empty_s3_bucket(s3, bucket_name)
                    s3.delete_bucket(Bucket=bucket_name)
                    results['buckets'].append({'name': bucket_name, 'action': 'deleted'})
                    logger.info(f"Deleted S3 bucket: {bucket_name}")
                    
            except s3.exceptions.NoSuchTagSet:
                # Bucket has no tags, skip
                continue
            except Exception as e:
                results['errors'].append(f"Failed to process bucket {bucket_name}: {str(e)}")
        
    except Exception as e:
        results['errors'].append(str(e))
        logger.error(f"Error cleaning S3 resources: {str(e)}")
    
    return results

def cleanup_iam_resources_by_session(session_id):
    """Clean up IAM roles and policies created for testing"""
    
    iam = boto3.client('iam')
    results = {
        'resources': [],
        'errors': []
    }
    
    try:
        # Clean up roles
        roles_response = iam.list_roles()
        
        for role in roles_response['Roles']:
            role_name = role['RoleName']
            
            # Check if role was created for our session (by naming convention)
            if session_id in role_name or role_name.startswith('security-test-'):
                try:
                    # Detach managed policies
                    attached_policies = iam.list_attached_role_policies(RoleName=role_name)
                    for policy in attached_policies['AttachedPolicies']:
                        iam.detach_role_policy(RoleName=role_name, PolicyArn=policy['PolicyArn'])
                    
                    # Delete inline policies
                    inline_policies = iam.list_role_policies(RoleName=role_name)
                    for policy_name in inline_policies['PolicyNames']:
                        iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
                    
                    # Remove role from instance profiles
                    instance_profiles = iam.list_instance_profiles_for_role(RoleName=role_name)
                    for profile in instance_profiles['InstanceProfiles']:
                        iam.remove_role_from_instance_profile(
                            InstanceProfileName=profile['InstanceProfileName'],
                            RoleName=role_name
                        )
                        # Delete the instance profile if it was created for testing
                        if session_id in profile['InstanceProfileName']:
                            iam.delete_instance_profile(InstanceProfileName=profile['InstanceProfileName'])
                    
                    # Delete the role
                    iam.delete_role(RoleName=role_name)
                    results['resources'].append({'type': 'IAM Role', 'name': role_name, 'action': 'deleted'})
                    
                except Exception as e:
                    results['errors'].append(f"Failed to delete IAM role {role_name}: {str(e)}")
        
    except Exception as e:
        results['errors'].append(str(e))
        logger.error(f"Error cleaning IAM resources: {str(e)}")
    
    return results

def cleanup_vpc_resources(ec2, vpc_id, session_id):
    """Clean up VPC and all its associated resources"""
    
    results = {
        'success': False,
        'resources': [],
        'errors': []
    }
    
    try:
        logger.info(f"Cleaning up VPC: {vpc_id}")
        
        # Delete internet gateways
        igws = ec2.describe_internet_gateways(
            Filters=[
                {'Name': 'attachment.vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        for igw in igws['InternetGateways']:
            try:
                ec2.detach_internet_gateway(InternetGatewayId=igw['InternetGatewayId'], VpcId=vpc_id)
                ec2.delete_internet_gateway(InternetGatewayId=igw['InternetGatewayId'])
                results['resources'].append({'type': 'Internet Gateway', 'id': igw['InternetGatewayId'], 'action': 'deleted'})
            except Exception as e:
                results['errors'].append(f"Failed to delete IGW {igw['InternetGatewayId']}: {str(e)}")
        
        # Delete subnets
        subnets = ec2.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        for subnet in subnets['Subnets']:
            try:
                ec2.delete_subnet(SubnetId=subnet['SubnetId'])
                results['resources'].append({'type': 'Subnet', 'id': subnet['SubnetId'], 'action': 'deleted'})
            except Exception as e:
                results['errors'].append(f"Failed to delete subnet {subnet['SubnetId']}: {str(e)}")
        
        # Delete route tables (except main route table)
        route_tables = ec2.describe_route_tables(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'tag:SessionId', 'Values': [session_id]}
            ]
        )
        
        for rt in route_tables['RouteTables']:
            # Skip main route table
            if not any(assoc.get('Main', False) for assoc in rt.get('Associations', [])):
                try:
                    ec2.delete_route_table(RouteTableId=rt['RouteTableId'])
                    results['resources'].append({'type': 'Route Table', 'id': rt['RouteTableId'], 'action': 'deleted'})
                except Exception as e:
                    results['errors'].append(f"Failed to delete route table {rt['RouteTableId']}: {str(e)}")
        
        # Delete the VPC
        try:
            ec2.delete_vpc(VpcId=vpc_id)
            results['resources'].append({'type': 'VPC', 'id': vpc_id, 'action': 'deleted'})
            results['success'] = True
            logger.info(f"Successfully deleted VPC: {vpc_id}")
        except Exception as e:
            results['errors'].append(f"Failed to delete VPC {vpc_id}: {str(e)}")
        
    except Exception as e:
        results['errors'].append(str(e))
        logger.error(f"Error cleaning up VPC {vpc_id}: {str(e)}")
    
    return results

def wait_for_instance_termination(ec2, instance_id, timeout=300):
    """Wait for EC2 instance to be terminated"""
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            state = response['Reservations'][0]['Instances'][0]['State']['Name']
            
            if state == 'terminated':
                logger.info(f"Instance {instance_id} is terminated")
                return True
            
            time.sleep(10)
            
        except Exception as e:
            logger.warning(f"Error checking instance state during termination: {str(e)}")
            break
    
    logger.warning(f"Timeout waiting for instance {instance_id} termination")
    return False

def empty_s3_bucket(s3, bucket_name):
    """Empty an S3 bucket by deleting all objects"""
    
    try:
        # List and delete all objects
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)
        
        for page in pages:
            if 'Contents' in page:
                objects = [{'Key': obj['Key']} for obj in page['Contents']]
                if objects:
                    s3.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': objects}
                    )
        
        # Delete all object versions (if versioning is enabled)
        try:
            versions_paginator = s3.get_paginator('list_object_versions')
            version_pages = versions_paginator.paginate(Bucket=bucket_name)
            
            for page in version_pages:
                versions = []
                if 'Versions' in page:
                    versions.extend([{'Key': v['Key'], 'VersionId': v['VersionId']} for v in page['Versions']])
                if 'DeleteMarkers' in page:
                    versions.extend([{'Key': dm['Key'], 'VersionId': dm['VersionId']} for dm in page['DeleteMarkers']])
                
                if versions:
                    s3.delete_objects(
                        Bucket=bucket_name,
                        Delete={'Objects': versions}
                    )
        except Exception:
            # Versioning might not be enabled
            pass
            
    except Exception as e:
        logger.error(f"Error emptying S3 bucket {bucket_name}: {str(e)}")
        raise

def cleanup_old_test_resources(max_age_hours=24):
    """Clean up test resources older than specified age (safety mechanism)"""
    
    cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
    
    try:
        ec2 = boto3.client('ec2')
        
        # Find old test instances
        instances = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Purpose', 'Values': ['SecurityBaseline-Testing']},
                {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping', 'stopped']}
            ]
        )
        
        old_instances = []
        for reservation in instances['Reservations']:
            for instance in reservation['Instances']:
                launch_time = instance['LaunchTime'].replace(tzinfo=None)
                if launch_time < cutoff_time:
                    old_instances.append(instance['InstanceId'])
        
        if old_instances:
            ec2.terminate_instances(InstanceIds=old_instances)
            logger.info(f"Cleaned up {len(old_instances)} old test instances")
        
    except Exception as e:
        logger.error(f"Error cleaning up old test resources: {str(e)}")
