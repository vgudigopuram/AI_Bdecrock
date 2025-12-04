# Security Baseline Automation - Lambda Functions

## Overview

This directory contains all the Lambda functions required for the Agentic GenAI Security Baseline Automation system.

## System Architecture

```
User Request → Orchestrator → Requirement Processor → Resource Manager → Validator → Config Refiner → Cleanup
```

## Lambda Functions

### 1. `security_baseline_orchestrator.py`
**Main entry point** - Coordinates the entire security baseline generation process
- **Timeout**: 15 minutes
- **Memory**: 512 MB
- **Responsibilities**: 
  - Invoke Bedrock for requirement generation
  - Coordinate processing of multiple requirements
  - Generate final reports

### 2. `requirement_processor.py`
**Individual requirement handler** - Manages the test-validate-refine loop for each requirement
- **Timeout**: 5 minutes
- **Memory**: 256 MB
- **Responsibilities**:
  - Deploy test resources
  - Run validation tests
  - Coordinate refinement attempts
  - Return validated or failed requirements

### 3. `ec2_resource_manager.py`
**AWS EC2 resource management** - Creates and manages EC2 instances for testing
- **Timeout**: 10 minutes
- **Memory**: 256 MB
- **Responsibilities**:
  - Create test VPCs, subnets, security groups
  - Launch EC2 instances with specific configurations
  - Apply security settings from requirements
  - Provide instance details for testing

### 4. `imds_validator.py`
**IMDS security validation** - Tests Instance Metadata Service configurations
- **Timeout**: 5 minutes
- **Memory**: 256 MB
- **Responsibilities**:
  - Validate MetadataOptions settings
  - Test IMDSv1 blocking
  - Verify IMDSv2 token requirements
  - Check hop limit configurations

### 5. `config_refiner.py`
**Configuration refinement** - Uses Bedrock to improve failed configurations
- **Timeout**: 5 minutes
- **Memory**: 256 MB
- **Responsibilities**:
  - Analyze test failure reasons
  - Use Bedrock AI to generate improved configurations
  - Provide fallback refinement logic
  - Return refined settings for retry

### 6. `resource_cleanup.py`
**Resource cleanup** - Removes all test resources to prevent cost accumulation
- **Timeout**: 15 minutes
- **Memory**: 256 MB
- **Responsibilities**:
  - Clean up EC2 instances, VPCs, security groups
  - Remove S3 buckets and IAM roles
  - Handle session-based cleanup
  - Emergency cleanup of old resources

## Key Features

### Bedrock Integration
- Uses Claude 3 Sonnet for requirement generation and config refinement
- Structured prompts for consistent JSON responses
- Error handling and fallback logic

### AWS Resource Management
- Isolated test environments using VPCs
- Proper resource tagging for easy cleanup
- Security group management
- Instance metadata configuration

### Validation Testing
- IMDS configuration validation
- Network security testing
- Encryption verification
- Access control validation

### Error Handling & Retry Logic
- Maximum 3 refinement attempts per requirement
- Graceful failure handling
- Comprehensive logging
- Resource cleanup on failures

## Deployment

Use the `deploy_lambdas.py` script to deploy all functions:

```bash
python deployment/deploy_lambdas.py
```

## Required Permissions

The Lambda functions need the following AWS permissions:
- **EC2**: Full access for resource management
- **IAM**: Role and policy management for test resources
- **S3**: Bucket management for testing
- **Bedrock**: Model invocation permissions
- **Lambda**: Function invocation for coordination
- **Logs**: CloudWatch logging

## Testing Flow Example

1. **Input**: User requests "EC2" security baseline
2. **Generation**: Bedrock generates requirements (IMDS, encryption, network)
3. **Processing**: Each requirement processed in parallel
4. **Testing**: 
   - Deploy EC2 instance with specific config
   - Run security validation tests
   - Analyze results
5. **Refinement**: If tests fail, refine configuration and retry
6. **Cleanup**: Remove all test resources
7. **Output**: Validated security requirements with test results

## Monitoring

- All functions log to CloudWatch
- Session IDs for tracking related resources
- Test result details for debugging
- Performance metrics and error rates

## Cost Optimization

- Automatic resource cleanup after testing
- Minimal instance sizes (t3.micro)
- Short-lived test resources
- Emergency cleanup for old resources
- Session-based resource grouping
