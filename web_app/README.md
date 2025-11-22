# Wind Farm Development Agent

A containerized web application for wind farm site analysis and development using AI agents.

## Features

- **Terrain Analysis**: Analyze terrain conditions and buildable areas
- **Layout Generation**: Create optimized turbine layouts
- **Wake Simulation**: Run wind farm performance simulations
- **Executive Reports**: Generate comprehensive analysis reports
- **Interactive Web Interface**: React frontend with real-time agent communication

## Prerequisites

- Docker
- AWS credentials with access to:
  - Amazon Bedrock (Claude models)
  - S3 (for file storage)
  - SSM Parameter Store

## Build and Run

### 1. Build the Container

```bash
docker build -t alonsodecosio/wind-farm-app:agentcore --platform='linux/amd64' .
```

### 2. Run the Container Locally

```bash
docker run -p 8080:8080 \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
  -e AWS_DEFAULT_REGION=us-west-2 \
  alonsodecosio/wind-farm-app:agentcore
```

### 3. Access the Application

**Local Development:**
Open your browser and navigate to: `http://<host-dns>:8080`

**ECS Deployment:**
Use the Load Balancer URL from the CloudFormation stack outputs

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS access key ID | Required |
| `AWS_SECRET_ACCESS_KEY` | AWS secret access key | Required |
| `AWS_SESSION_TOKEN` | AWS session token (if using temporary credentials) | Optional |
| `AWS_DEFAULT_REGION` | AWS region for services | `us-west-2` |

## Usage

1. Enter coordinates for your wind farm site
2. Specify requirements (capacity, setbacks, turbine spacing)
3. The agent will:
   - Analyze terrain and buildable areas
   - Generate optimized turbine layouts
   - Run wake simulations
   - Create executive reports with recommendations

## Example Requests

- "Analyze terrain at 35.067482, -101.395466 with 100m setback"
- "Create a wind farm with 30MW capacity at 35.067482, -101.395466. Turbines need 100m setback and 700m spacing. Use turbine IEA_Reference_3.4MW_130"

## Architecture

- **Frontend**: React with TypeScript
- **Backend**: FastAPI with Python
- **AI Models**: Amazon Bedrock Claude
- **Storage**: AWS S3
- **Configuration**: AWS SSM Parameter Store
