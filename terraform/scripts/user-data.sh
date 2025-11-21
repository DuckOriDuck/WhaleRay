#!/bin/bash
# ============================================
# WhaleRay ECS Instance User Data
# ============================================
# This script initializes ECS instances and deploys the nginx configuration

set -e

# Configure ECS Agent
echo "ECS_CLUSTER=${cluster_name}" >> /etc/ecs/ecs.config
echo "ECS_ENABLE_CONTAINER_METADATA=true" >> /etc/ecs/ecs.config
echo "ECS_ENABLE_TASK_IAM_ROLE=true" >> /etc/ecs/ecs.config
echo "ECS_ENABLE_TASK_IAM_ROLE_NETWORK_HOST=true" >> /etc/ecs/ecs.config

# Log completion
echo "WhaleRay ECS instance initialization completed at $(date)" >> /var/log/whaleray-init.log
