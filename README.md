# WhaleRay : Github Compatible One-click Deployment PaaS
## -> [WhaleRay](https://whaleray.oriduckduck.site/)<-
Ship to AWS in seconds with WhaleRay’s seamless GitHub App integration. Just connect your repository, click deploy, and let us handle the rest


#### Preliminary entry for Softbank Hackathon 2025 in Korea
<img width="1987" height="334" alt="image" src="https://github.com/user-attachments/assets/4a3c9ec5-53b3-4166-80b7-9b3d95e0676f" />


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

## Main Features

#### one click depoyment
- select authorized repository & branch, hit deploy button 
<img width="2069" height="1482" alt="image" src="https://github.com/user-attachments/assets/15e7ae2f-bb84-4b5d-b220-ca82eb242d9a" />
- you can see the real-time deployment state on the deployment tab.(INSPECTING, BUILDING, RUNNING, FAILED)
<img width="2094" height="504" alt="image" src="https://github.com/user-attachments/assets/4ae51dc3-8122-4daf-b965-03c76858025f" />
- you can also see the real time pulled logs from AWS CodeBuild
<img width="2091" height="1556" alt="image" src="https://github.com/user-attachments/assets/d821a214-2fb5-4ecd-8566-f3d932584cef" />
- if build suceeds, the deployment state turns to "RUNNING"
<img width="2077" height="490" alt="image" src="https://github.com/user-attachments/assets/bd703bb9-fbc7-4630-994b-23a7d3aa4850" />
- you can view the deployed service in the unique subdomain of our service, each service is unique with one repository, each owning it's own fixed domain under
```
https://service.whaleray.oriduckduck.site/{user id}-{User or Organization name}-{repository name}
```
format.
so if you deploy the service from the same branch, pre-deployed service is replaced by the post-build result.
- and the 
<img width="2119" height="391" alt="image" src="https://github.com/user-attachments/assets/3f5d52a1-7e4b-4500-81f8-39849b336a6b" />
<img width="2879" height="1636" alt="image" src="https://github.com/user-attachments/assets/932da05a-84bb-4106-aa08-59e090509621" />


## API Documentations

## Preview


```

## License

MIT
