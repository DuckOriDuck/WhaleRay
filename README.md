# WhaleRay : Github Compatible One-click Deployment PaaS
Ship to AWS in seconds with WhaleRay’s seamless GitHub App integration. Just connect your repository, click deploy, and let us handle the rest

*The Whaleray server is temporarily offline. It is scheduled to be integrated with '[Ducksnest](https://github.com/DuckOriDuck/ducksnest-homelab)' to enable temporary deployments on my own Homelab Infrastructure.*

#### 한국어 문서는 [여기서](README-KOREAN.md) 보시면 됩니다.

#### Preliminary entry for Softbank Hackathon 2025 in Korea
<img width="1987" height="334" alt="image" src="https://github.com/user-attachments/assets/4a3c9ec5-53b3-4166-80b7-9b3d95e0676f" />

# Key Features
## 1. Secure GitHub App Integration - No Token Required

Authenticate with GitHub OAuth in one click - no personal access tokens needed. WhaleRay never stores your credentials, eliminating token exposure risks while providing secure repository access.

## 2. One-Click Zero-Config Deployment
- Deploy your Spring Boot applications without writing a single line of Dockerfile or build script. The system automatically analyzes your repository and configures the optimal build environment.
<img width="2069" height="1482" alt="image" src="https://github.com/user-attachments/assets/15e7ae2f-bb84-4b5d-b220-ca82eb242d9a" />

### Auto-Detection Strategy

- **Framework Detection**: Automatically identifies Spring Boot projects by detecting `build.gradle` or `pom.xml` in your repository
- **Smart Image Generation**: When no `Dockerfile` is present, the system automatically injects an optimized image based on Eclipse Temurin JDK 17 (Alpine)
- **Custom Dockerfile Support**: If you include a custom `Dockerfile`, it takes priority and is used for the build process

### Build Process Injection

- Essential metadata such as `deployment_id` and `ECR_IMAGE_URI` are dynamically injected as environment variables during the build process
- Automatically detects Gradle Wrapper (`gradlew`) presence and adjusts build commands accordingly

### Real-Time Deployment Monitoring

Track your deployment progress through multiple states: **INSPECTING**, **BUILDING**, **RUNNING**, and **FAILED**.

<img width="2094" height="504" alt="image" src="https://github.com/user-attachments/assets/4ae51dc3-8122-4daf-b965-03c76858025f" />

*Monitor deployment state in real-time on the deployment tab*

<img width="2091" height="1556" alt="image" src="https://github.com/user-attachments/assets/d821a214-2fb5-4ecd-8566-f3d932584cef" />

*View real-time logs pulled directly from AWS CodeBuild*

<img width="2077" height="490" alt="image" src="https://github.com/user-attachments/assets/bd703bb9-fbc7-4630-994b-23a7d3aa4850" />

*Deployment state automatically updates to "RUNNING" upon successful build*

- you can view the deployed service in the unique subdomain of our service, each service is unique with one repository, each owning it's own fixed domain under

## 3. Dynamic Routing & Zero Downtime Updates

Each service receives a unique subdomain and path, with seamless version updates that ensure zero downtime during deployment.

### Unique Service URL Structure

Every deployed service is accessible through a fixed, unique domain:
```
https://service.whaleray.oriduckduck.site/{user-id}-{organization-name}-{repository-name}
```

<img width="2119" height="391" alt="image" src="https://github.com/user-attachments/assets/3f5d52a1-7e4b-4500-81f8-39849b336a6b" />
<img width="2879" height="1636" alt="image" src="https://github.com/user-attachments/assets/932da05a-84bb-4106-aa08-59e090509621" />

*Access your deployed service through its unique subdomain*

When you deploy from the same branch, the pre-existing service is seamlessly replaced by the new build result.

### Intelligent Traffic Routing

- **Nginx Router**: Uses regex patterns (`^/(?<deployment_id>github_[^/]+)`) to identify target services and route traffic accordingly
- **Service Discovery (AWS Cloud Map)**: ECS tasks automatically register their private IPs in the `whaleray.local` namespace, enabling Nginx to dynamically discover container IPs as they change

### Rolling Deployment Strategy

- ECS services are configured with **Minimum Healthy Percent: 100%** and **Maximum Percent: 200%**
- During deployment, new containers reach 100% healthy (Running) state before old containers begin draining and termination
- This strategy guarantees zero downtime updates, ensuring continuous service availability

## 4. AI-Powered Build Log Analysis

When deployments fail, there's no need to manually parse through thousands of log lines. An AI agent integrated with AWS Bedrock diagnoses the root cause for you.

<img width="2030" height="521" alt="image" src="https://github.com/user-attachments/assets/a1ac66ed-4da4-4291-8f18-8f04b3629b4f" />

*Trigger AI-powered analysis with a single click*

### Smart Log Filtering

- **Cost & Speed Optimization**: Instead of sending entire logs to the LLM, a Lambda preprocessor intelligently filters the data
- **Noise Reduction**: Removes unnecessary metadata (e.g., `START RequestId`) using regex patterns
- **Context Extraction**: Focuses on the last 50 lines of logs where error context is most concentrated

### Claude 3 Haiku Integration
  
<img width="2051" height="1490" alt="image" src="https://github.com/user-attachments/assets/9f22da89-2876-44d6-b62f-c4c9227ec647" />
<img width="2032" height="1485" alt="image" src="https://github.com/user-attachments/assets/6fbd0782-61b1-4ee0-8cd2-fd1c6b664060" />
*Receive structured analysis with identified issues and actionable recommendations*

- Extracted logs are sent to Claude 3 with a DevOps engineer persona injected into the prompt
- Returns structured JSON output (`status`, `issues`, `recommendations`) instead of plain text, enabling immediate visualization in the frontend
- The entire process runs synchronously, delivering analysis reports within seconds of clicking the button


## Tech Stack:
- **Cloud**: AWS
- **IaC**: Terraform
- **Authentication**: GitHub App
- **Backend**: API Gateway HTTP API + Lambda + Bedrock
- **User Deployment Platform**: ECS Fargate
- **Subnet Domain Routing**: Application Load Balancer + NginX + CloudMap
- **Database(Server State Management)**: DynamoDB (Users, Deployments, Services)
- **Frontend**: React + Vite

## Architecture
<img width="1100" height="935" alt="image" src="https://github.com/user-attachments/assets/4daa2cfc-395b-4c48-9c8a-9c7939dcac7d" />


## License

MIT
