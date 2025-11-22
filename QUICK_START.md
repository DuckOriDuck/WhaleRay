# WhaleRay Dynamic Proxy - Quick Start Guide

## 🚀 What Was Built

A **Dynamic Nginx Reverse Proxy** on AWS ECS (EC2) that routes requests to backend services using Cloud Map service discovery.

```
Internet
   ↓
[ALB] /services/abc123/api/users
   ↓
[Nginx Router] (2-20 tasks, auto-scales)
   ↓
[Cloud Map DNS] abc123.whaleray.local → 10.0.x.x
   ↓
[Backend Service] Your deployed app
```

---

## 📦 What You Got

### New Files (6 total)

1. **service-discovery.tf** - Cloud Map namespace `whaleray.local`
2. **router.tf** - Nginx router service with auto-scaling
3. **nginx.conf** - Dynamic routing configuration
4. **user-data.sh** - EC2 initialization script
5. **ROUTER_ARCHITECTURE.md** - Detailed documentation
6. **IMPLEMENTATION_SUMMARY.md** - Implementation details

### Modified Files (2 total)

1. **ecs.tf** - Updated capacity provider (90% target, disabled termination)
2. **outputs.tf** - Added router service name and namespace outputs

---

## ⚡ Deploy Now

```bash
cd /root/project/WhaleRay/terraform

# Validate configuration
terraform validate

# See what will be created
terraform plan

# Deploy everything
terraform apply
```

---

## 🧪 Test It

### 1. Get ALB DNS Name

```bash
terraform output alb_dns
```

### 2. Test Health Endpoint

```bash
curl http://<alb-dns>/services/test/health
# Expected: 502 (service not found) or 200 (if test service exists)
```

### 3. Test Routing to Real Service

Once you deploy a service with ID `my-deployment-123`:

```bash
curl http://<alb-dns>/services/my-deployment-123/api/status
# This proxies to: http://my-deployment-123.whaleray.local:3000/api/status
```

---

## 🎯 How It Works

### URL Pattern

```
/services/{deploymentId}/{path}
```

**Example:**
- Input: `/services/abc123/api/users?page=1`
- Nginx extracts: `deploymentId=abc123`, `path=/api/users?page=1`
- Proxies to: `http://abc123.whaleray.local:3000/api/users?page=1`

### Auto-Scaling

**Level 1: Infrastructure (EC2)**
- Scales when cluster reaches **90% capacity**
- Range: **1-10 instances**

**Level 2: Tasks (Nginx)**
- Scales when CPU > **60%**
- Range: **2-20 tasks**

---

## 📊 Check Status

### Router Service

```bash
aws ecs describe-services \
  --cluster whaleray-cluster \
  --services whaleray-router \
  --region ap-northeast-2
```

### Cloud Map Namespace

```bash
aws servicediscovery list-namespaces --region ap-northeast-2
```

### ALB Target Health

```bash
aws elbv2 describe-target-health \
  --target-group-arn $(terraform output -raw router_target_group_arn) \
  --region ap-northeast-2
```

---

## 🔧 Configuration Summary

| Component | Setting | Value |
|-----------|---------|-------|
| **Namespace** | DNS Name | `whaleray.local` |
| **Router** | Min Tasks | 2 |
| **Router** | Max Tasks | 20 |
| **Router** | CPU Threshold | 60% |
| **ASG** | Min Instances | 1 |
| **ASG** | Max Instances | 10 |
| **ASG** | Target Capacity | 90% |
| **Placement** | Strategy | binpack on memory |
| **ALB Rule** | Path Pattern | `/services/*` |
| **ALB Rule** | Priority | 100 |

---

## 🛠️ Troubleshooting

### Problem: Router tasks stuck in PENDING

**Solution:** Check if EC2 instances are launching
```bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names whaleray-ecs-asg \
  --region ap-northeast-2
```

### Problem: 502 errors for all requests

**Solution:** Check if DNS resolver is working
```bash
# SSH into an ECS instance
aws ssm start-session --target <instance-id>

# Test DNS resolution
nslookup test.whaleray.local 169.254.169.253
```

### Problem: Router not registering with ALB

**Solution:** Check security groups
```bash
# Router SG should allow port 80 from ALB SG
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=whaleray-router" \
  --region ap-northeast-2
```

---

## 📚 Read More

- **Architecture Details:** [ROUTER_ARCHITECTURE.md](./ROUTER_ARCHITECTURE.md)
- **Implementation Summary:** [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)
- **AWS ECS Capacity Providers:** https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-capacity-providers.html
- **AWS Cloud Map:** https://docs.aws.amazon.com/cloud-map/latest/dg/what-is-cloud-map.html

---

## ✅ Requirements Checklist

- [x] Cloud Map namespace `whaleray.local`
- [x] ECS EC2 launch type
- [x] 2-Stage auto-scaling (infrastructure + tasks)
- [x] Capacity Provider (90% target, termination disabled)
- [x] ALB listener rule for `/services/*`
- [x] Nginx dynamic routing with regex
- [x] DNS resolver: 169.254.169.253
- [x] Binpack placement strategy on memory
- [x] Task auto-scaling (60% CPU, 2-20 tasks)
- [x] Security groups (ALB → Router only)
- [x] Dynamic port mapping (hostPort: 0)

---

## 🎉 You're Ready!

Run `terraform apply` to deploy the Dynamic Proxy Architecture.

Questions? Check [ROUTER_ARCHITECTURE.md](./ROUTER_ARCHITECTURE.md) for detailed documentation.
