# Kubernetes Deployment (EKS-ready)

This folder contains a first-pass Kubernetes deployment for the current app stack:

- `client`
- `platform-api`
- `ai-agent-service`
- `mysql`, `mongodb`, `redis`
- `kafka`, `zookeeper`, `kafka-ui`

Main manifest: `infrastructure/k8s/linkedin-stack.yaml`

## 1) Build and push images (you run these)

Use your ECR registry URI and tag:

```bash
AWS_ACCOUNT_ID=123456789012
AWS_REGION=us-west-2
ECR_BASE="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/linkedin-ds"
TAG=v1

docker build -t "$ECR_BASE/platform-api:$TAG" services/platform-api
docker build -t "$ECR_BASE/ai-agent-service:$TAG" ai-agents
docker build -t "$ECR_BASE/client:$TAG" client
docker build -t "$ECR_BASE/mysql:$TAG" databases/mysql
docker build -t "$ECR_BASE/mongodb:$TAG" databases/mongodb

docker push "$ECR_BASE/platform-api:$TAG"
docker push "$ECR_BASE/ai-agent-service:$TAG"
docker push "$ECR_BASE/client:$TAG"
docker push "$ECR_BASE/mysql:$TAG"
docker push "$ECR_BASE/mongodb:$TAG"
```

Then replace `YOUR_ECR_REPO/...:latest` values in `linkedin-stack.yaml`.

## 2) Create/update Kubernetes secret values

Edit `stringData` in `linkedin-secrets` inside `linkedin-stack.yaml`:

- `MYSQL_ROOT_PASSWORD`
- `MYSQL_PASSWORD`
- `MONGO_PASSWORD`
- `JWT_SECRET`
- `GROQ_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

## 3) Apply manifests

```bash
kubectl apply -f infrastructure/k8s/linkedin-stack.yaml
kubectl get pods -n linkedin
kubectl get svc -n linkedin
kubectl get ingress -n linkedin
```

## 4) Seed data

Run seeding once after MySQL is healthy and reachable from where you run the seed script.

If you run it from your local machine, temporarily port-forward MySQL:

```bash
kubectl port-forward -n linkedin svc/mysql 3307:3306
```

In another terminal:

```bash
MYSQL_HOST=127.0.0.1 MYSQL_PORT=3307 python databases/seed.py --keep
```

## Notes

- This is a practical first pass for demo and class deployment.
- For production hardening, move stateful services to managed AWS equivalents:
  - RDS (MySQL)
  - DocumentDB/Atlas (MongoDB)
  - ElastiCache (Redis)
  - MSK (Kafka)
