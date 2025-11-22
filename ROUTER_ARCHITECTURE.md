# WhaleRay Dynamic Proxy Architecture

## Overview

This document describes the Dynamic Proxy Architecture implemented for WhaleRay on AWS ECS (EC2 Launch Type). The architecture enables dynamic routing of HTTP requests to backend services using Cloud Map service discovery and an Nginx reverse proxy.

## Architecture Components

### 1. Service Discovery (Cloud Map)

**File:** `service-discovery.tf`

- **Resource:** `aws_service_discovery_private_dns_namespace`
- **Namespace:** `whaleray.local`
- **Type:** Private DNS within VPC
- **Purpose:** Enables services to discover each other using DNS names like `{deploymentId}.whaleray.local`

### 2. ECS Infrastructure with 2-Stage Auto Scaling

**File:** `ecs.tf`

The infrastructure implements **2-Stage Auto Scaling**:

#### Stage 1: Infrastructure Scaling (ECS Capacity Provider)
- **Target Capacity:** 90% (scales out when cluster capacity reaches 90%)
- **ASG Range:** Min 1, Max 10 instances
- **Instance Type:** `t3.small` (configurable via `var.ecs_instance_type`)
- **Managed Termination:** Disabled (allows ECS to terminate instances)

When task demand increases and cluster capacity reaches 90%, the Capacity Provider automatically adds EC2 instances to the Auto Scaling Group.

#### Stage 2: Task Scaling (Application Auto Scaling)
- **Metric:** `ECSServiceAverageCPUUtilization`
- **Target:** 60% CPU
- **Task Range:** Min 2, Max 20 tasks
- **Cooldown:** 60s scale-out, 300s scale-in

When the router service CPU exceeds 60%, additional router tasks are launched on available instances.

### 3. WhaleRay Router (Nginx Reverse Proxy)

**File:** `router.tf`

#### Components:

**ALB Target Group:**
- Name Prefix: `wrrt-` (WhaleRay Router)
- Target Type: `instance` (required for EC2 launch type)
- Health Check: `/health` endpoint

**ALB Listener Rule:**
- Priority: 100
- Path Pattern: `/services/*`
- Action: Forward to router target group

**Security Group:**
- **Ingress:** Port 80 from ALB only
- **Egress:** All traffic (to reach backend services)

**ECS Task Definition:**
- **Family:** `whaleray-router`
- **Network Mode:** `bridge` (required for EC2 + dynamic ports)
- **CPU:** 256
- **Memory:** 512 MB
- **Container:** `nginx:latest`
- **Port Mapping:** Container port 80, Host port 0 (dynamic)
- **Volume Mount:** `/etc/whaleray/nginx.conf` → `/etc/nginx/nginx.conf`

**ECS Service:**
- **Launch Type:** EC2
- **Desired Count:** 2 (High Availability)
- **Placement Strategy:** `binpack` on `memory` (efficient resource usage)
- **Load Balancer:** Connected to router target group

### 4. Nginx Configuration

**File:** `nginx.conf`

#### Key Features:

**DNS Resolver:**
```nginx
resolver 169.254.169.253 valid=10s ipv6=off;
```
Uses AWS VPC DNS to resolve Cloud Map service names dynamically.

**Dynamic Routing Logic:**
```nginx
location ~ ^/services/(?<deployment_id>[^/]+)(?<request_path>/.*)?$ {
    set $backend_host "${deployment_id}.whaleray.local";
    set $backend_port "3000";
    set $backend_url "http://${backend_host}:${backend_port}";

    proxy_pass $backend_url$request_path$is_args$args;
}
```

**Example Routing:**
- Request: `GET /services/abc123/api/users?page=1`
- Proxies to: `http://abc123.whaleray.local:3000/api/users?page=1`

#### Endpoints:

- **`/health`**: Returns `200 OK` for health checks
- **`/services/{deploymentId}/*`**: Dynamic proxy to backend service
- **`/*`**: Returns `404 Not Found`

### 5. User Data Script

**File:** `user-data.sh`

Executed on each ECS instance launch:
1. Configures ECS agent with cluster name
2. Creates `/etc/whaleray/` directory
3. Deploys `nginx.conf` to `/etc/whaleray/nginx.conf`
4. Sets proper file permissions

## Request Flow

1. **Client Request:**
   ```
   GET https://whaleray.example.com/services/deployment-123/api/data
   ```

2. **ALB Receives Request:**
   - ALB listener rule (priority 100) matches `/services/*`
   - Forwards to router target group

3. **Router (Nginx) Receives Request:**
   - Extracts `deployment_id` = `deployment-123`
   - Constructs backend URL: `http://deployment-123.whaleray.local:3000`

4. **DNS Resolution:**
   - Nginx queries AWS VPC DNS (169.254.169.253)
   - Cloud Map resolves `deployment-123.whaleray.local` to backend service IP

5. **Proxy Request:**
   - Nginx proxies to backend: `http://<backend-ip>:3000/api/data`

6. **Response:**
   - Backend responds to Nginx
   - Nginx forwards response to client via ALB

## Auto Scaling Behavior

### Scenario 1: Increased Traffic to Router

1. Router tasks experience CPU > 60%
2. Application Auto Scaling adds more router tasks
3. If no capacity available on existing instances, Capacity Provider adds EC2 instances
4. New router tasks are placed using `binpack` strategy

### Scenario 2: New Deployments

1. User deploys a new service
2. ECS deployer creates task with Cloud Map service registration
3. Service registers as `{deploymentId}.whaleray.local` in Cloud Map
4. Router can immediately resolve and proxy to the new service

## Deployment

### Initial Deployment

```bash
cd /root/project/WhaleRay/terraform
terraform init
terraform plan
terraform apply
```

### Files Created

- `service-discovery.tf` - Cloud Map namespace
- `router.tf` - Router service, target group, and auto scaling
- `nginx.conf` - Nginx configuration
- `user-data.sh` - EC2 instance initialization script
- `ROUTER_ARCHITECTURE.md` - This documentation

### Files Modified

- `ecs.tf` - Updated capacity provider settings and user data
- `outputs.tf` - Added router and service discovery outputs

## Configuration Variables

All configuration uses existing variables from `variables.tf`:

- `var.project_name` - Project name prefix (default: "whaleray")
- `var.aws_region` - AWS region (default: "ap-northeast-2")
- `var.vpc_cidr` - VPC CIDR block
- `var.availability_zones` - AZs for multi-AZ deployment
- `var.ecs_instance_type` - EC2 instance type
- `var.ecs_min_size` - Min ASG size (overridden to 1 in code)
- `var.ecs_max_size` - Max ASG size (overridden to 10 in code)

## Monitoring

### CloudWatch Metrics

**Infrastructure Scaling:**
- `AWS/ECS` → `CPUReservation` (cluster level)
- `AWS/ECS` → `MemoryReservation` (cluster level)

**Task Scaling:**
- `AWS/ECS` → `CPUUtilization` (service level)
- Router service will auto-scale based on this metric

**ALB Metrics:**
- `AWS/ApplicationELB` → `TargetResponseTime`
- `AWS/ApplicationELB` → `HTTPCode_Target_5XX_Count`

### Logs

**Router Logs:**
- CloudWatch Log Group: `/ecs/whaleray-router`
- Stream Prefix: `router`

**ECS Instance Initialization:**
- Log File: `/var/log/whaleray-init.log` (on EC2 instances)

## Security

### Network Security

1. **ALB Security Group:**
   - Ingress: 80, 443 from `0.0.0.0/0`
   - Egress: All

2. **Router Security Group:**
   - Ingress: Port 80 from ALB only
   - Egress: All (to reach backend services)

3. **ECS Instances Security Group:**
   - Ingress: All ports from ALB
   - Egress: All

### IAM Roles

- **Task Execution Role:** `whaleray-ecs-task-execution`
  - Pulls container images from ECR
  - Writes logs to CloudWatch

- **Task Role:** `whaleray-ecs-task`
  - Application-level permissions

- **Instance Role:** `whaleray-ecs-instance-role`
  - Allows EC2 instances to join ECS cluster

## Troubleshooting

### Router Cannot Resolve Backend Services

**Symptom:** 502 errors with "Service unavailable or deployment not found"

**Checks:**
1. Verify Cloud Map namespace exists: `aws servicediscovery list-namespaces`
2. Check if backend service is registered in Cloud Map
3. Verify DNS resolution from router container:
   ```bash
   docker exec <container-id> nslookup {deploymentId}.whaleray.local 169.254.169.253
   ```

### No EC2 Instances Launching

**Symptom:** Tasks stuck in PENDING state

**Checks:**
1. Verify ASG has desired capacity > 0
2. Check Capacity Provider status
3. Review ASG activity history in AWS Console
4. Check EC2 instance limits for your account

### Router Tasks Not Registering with ALB

**Symptom:** Router service shows 0 healthy targets

**Checks:**
1. Verify dynamic port mapping is working (check EC2 instance ports)
2. Check router task health status in ECS Console
3. Verify security group allows traffic from ALB
4. Check health check logs in router container

## Best Practices

1. **High Availability:** Keep minimum 2 router tasks across multiple AZs
2. **Cost Optimization:** Use `binpack` placement strategy to maximize instance utilization
3. **DNS Caching:** Nginx resolver cache is set to 10s for balance between performance and freshness
4. **Monitoring:** Set up CloudWatch alarms for 5XX errors and high latency
5. **Capacity Planning:** Monitor cluster reservation metrics to tune target capacity

## Future Enhancements

- [ ] Add HTTPS support between router and backend services
- [ ] Implement connection pooling for better performance
- [ ] Add request rate limiting per deployment
- [ ] Implement circuit breaker pattern for failing backends
- [ ] Add distributed tracing (X-Ray integration)
- [ ] Support multiple backend ports via Cloud Map service attributes
