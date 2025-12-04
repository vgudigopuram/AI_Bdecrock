# Agentic GenAI Security Baseline Implementation Plan

## Implementation Details

### Phase 1: MVP Implementation (EC2 Focus)
1. Basic requirement generation for EC2
2. Simple IMDS validation
3. Resource cleanup
4. Basic reporting

### Phase 2: Enhanced Validation
1. Multiple security controls
2. Configuration refinement loop
3. Comprehensive testing

### Phase 3: Multi-Service Support
1. S3 security baselines
2. RDS configurations
3. Lambda security settings

## Detailed Lambda Function Implementation

### 1. **security_baseline_orchestrator.py** (Main Entry Point)
**Purpose**: Coordinates the entire security baseline generation process
**Key Features**:
- Invokes Bedrock for requirement generation using Claude 3 Sonnet
- Manages parallel processing of multiple requirements
- Generates comprehensive final reports with success rates
- Handles error aggregation and cleanup coordination

**Bedrock Integration**:
```python
# Uses structured prompts to generate security requirements
prompt = f"""
Generate comprehensive security baseline requirements for AWS {service_name}.
For each requirement, provide:
1. objective: Category like "Access Control", "Encryption", "Network Security"
2. description: Clear description of what must be configured
3. configuration: Exact AWS configuration in JSON format
4. test_method: How to validate this requirement
5. priority: HIGH, MEDIUM, or LOW

Return as JSON with "requirements" array.
"""
```

### 2. **requirement_processor.py** (Test-Validate-Refine Loop)
**Purpose**: Implements the iterative improvement cycle for each requirement
**Key Features**:
- Maximum 3 refinement attempts per requirement
- Coordinates resource deployment, testing, and cleanup
- Handles failure analysis and configuration refinement
- Returns validated or failed requirements with detailed logs

**Flow**:
```
Deploy Resources → Run Tests → Analyze Results → [PASS] Clean & Return
                                              → [FAIL] Refine Config → Retry
```

### 3. **ec2_resource_manager.py** (AWS Resource Management)
**Purpose**: Creates and manages EC2 testing environments
**Key Features**:
- Creates isolated VPCs with proper networking (IGW, subnets, route tables)
- Applies security configurations from requirements (IMDS, encryption, networking)
- Manages instance lifecycle with proper state monitoring
- Implements comprehensive cleanup with dependency handling

**Resource Creation**:
- Test VPC (10.0.0.0/16 CIDR)
- Public subnet with Internet Gateway
- Security groups with minimal required access
- EC2 instances with specified security configurations

### 4. **imds_validator.py** (Security Testing)
**Purpose**: Validates Instance Metadata Service security configurations
**Key Features**:
- Tests MetadataOptions configuration (HttpTokens, HttpEndpoint)
- Validates IMDSv1 blocking effectiveness
- Verifies IMDSv2 token requirements
- Checks hop limit settings for container security

**Test Types**:
- Configuration verification
- Network accessibility tests
- Security control effectiveness
- Best practice compliance

### 5. **config_refiner.py** (AI-Powered Improvement)
**Purpose**: Uses Bedrock to analyze failures and improve configurations
**Key Features**:
- Detailed failure analysis with Bedrock AI
- Context-aware configuration improvements
- Fallback refinement logic for critical scenarios
- Progressive restriction approach (attempt 1: require tokens, attempt 2: disable endpoint)

**Bedrock Refinement Process**:
```python
# Analyzes test failures and generates improved configurations
prompt = f"""
Analyze this security configuration failure and provide a corrected version.
Original Config: {current_config}
Test Failures: {failed_tests}
Attempt: {attempt_number}

Return refined JSON configuration that addresses the failures.
"""
```

### 6. **resource_cleanup.py** (Cost Management)
**Purpose**: Comprehensive cleanup to prevent resource accumulation
**Key Features**:
- Session-based resource identification and cleanup
- Handles EC2, VPC, S3, and IAM resource removal
- Emergency cleanup for orphaned resources older than 24 hours
- Dependency-aware deletion order (instances → security groups → VPCs)

## System Flow Diagram

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User Input    │───▶│    Bedrock AI    │───▶│   Requirements  │
│  (Service Name) │    │  (Requirement    │    │   Generated     │
└─────────────────┘    │   Generation)    │    └─────────────────┘
                       └──────────────────┘              │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Final Report &  │◀───│  Orchestrator    │───▶│ For Each Req:   │
│   Cleanup       │    │  Coordinates     │    │ Process Loop    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Validated     │◀───│ Test Results     │◀───│ Deploy Test     │
│ Requirements    │    │   Analysis       │    │   Resources     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         ▲                        │                       │
         │               ┌────────▼────────┐              ▼
         │               │ Validation Pass? │    ┌─────────────────┐
         └───────────────│      Tests       │    │ Run Security    │
                         └─────────────────┘    │  Validation     │
                                  │             └─────────────────┘
                         ┌────────▼────────┐              │
                         │  Config Refiner │◀─────────────┘
                         │ (Bedrock AI +   │     (if fail)
                         │ Fallback Logic) │
                         └─────────────────┘
```

## Deployment Instructions

### Prerequisites
1. AWS CLI configured with appropriate permissions
2. Python 3.9+ environment
3. Bedrock model access enabled (Claude 3 Sonnet)

### Step 1: Deploy Lambda Functions
```powershell
cd c:\MSDE\bedrock
python deployment\deploy_lambdas.py
```

### Step 2: Test the System
```powershell
python examples\test_system.py
```

### Step 3: Verify Deployment
Check AWS Console for:
- 6 Lambda functions deployed
- IAM role with proper permissions
- CloudWatch logs for function execution

## Expected Deliverables

### 1. Working Prototype
- **Input**: Service name (e.g., "EC2")
- **Process**: Generate → Test → Validate → Refine → Report
- **Output**: Validated security requirements with test results

### 2. Demo Scenario (EC2 Example)
**Generated Requirements**:
1. ✅ IMDSv2 enforcement (`HttpTokens: "required"`)
2. ✅ No public IP assignment (`AssociatePublicIpAddress: false`)
3. ✅ EBS encryption (`Encrypted: true`)

**Validation Process**:
- Creates test EC2 instance with each configuration
- Attempts security tests (IMDS access, network checks)
- Reports PASS/FAIL with detailed test logs
- Demonstrates AI refinement when tests fail

### 3. Architecture Diagram
The system uses a **serverless, event-driven architecture**:
- **Bedrock AI** for intelligent requirement generation and refinement
- **Lambda functions** for scalable, cost-effective execution
- **VPC isolation** for secure testing environments
- **Automatic cleanup** to prevent cost accumulation

### 4. Value Proposition
- **Time Savings**: Automates manual security baseline creation (hours → minutes)
- **Validated Security**: Proves configurations work in practice, not just theory
- **AI-Powered**: Uses generative AI to create comprehensive, adaptive security requirements
- **Cost Effective**: Serverless architecture with automatic resource cleanup

## Success Metrics

1. **Accuracy**: % of generated requirements that pass validation on first attempt
2. **Coverage**: Number of security controls identified per AWS service
3. **Efficiency**: Time reduction compared to manual baseline creation
4. **Reliability**: Consistent requirement generation across multiple runs
5. **Cost**: Resource costs kept minimal through efficient cleanup

## Stretch Goals Implementation

### Knowledge Bases Integration
```python
# Enhanced prompting with AWS documentation context
bedrock_kb_client = boto3.client('bedrock-agent-runtime')
kb_response = bedrock_kb_client.retrieve_and_generate(
    input={'text': f'Security best practices for {service_name}'},
    retrieveAndGenerateConfiguration={
        'type': 'KNOWLEDGE_BASE',
        'knowledgeBaseConfiguration': {
            'knowledgeBaseId': 'your-knowledge-base-id'
        }
    }
)
```

### Advanced Reasoning
- Detailed explanation of each security requirement
- Attack scenario prevention mapping
- Compliance framework alignment (SOC2, PCI-DSS)

This implementation provides a complete, production-ready agentic AI system for automated security baseline generation and validation.
