# AWS DevOps mode

JARVIS can act as a DevOps copilot for AWS work. It does not store AWS credentials. It uses the AWS CLI profile already configured on your machine.

## Tools

| Tool | What it does | Approval |
| --- | --- | --- |
| `review_terraform` | Scans `.tf` files for open security groups, public S3, hardcoded secrets, missing backend | none (offline) |
| `review_dockerfile` | Unpinned base image, root user, secrets in ENV, `curl \| sh` | none (offline) |
| `review_cicd` | GitHub Actions and Jenkinsfile problems | none (offline) |
| `review_iam_policy` | Wildcard actions, PassRole on `*`, public principals | none (offline) |
| `devops_runbook` | Checklists for ECS, EKS, Terraform locks, Jenkins, ALB 5xx, IAM AccessDenied | none |
| `aws_read` | `describe-*`, `list-*`, `get-*`, `s3 ls` | none; refuses anything else |
| `aws_change` | Any other AWS CLI call | always asks first; `dry_run` shows the command |

Never auto-run: secret reads (Secrets Manager, SSM parameters, KMS decrypt, STS assume-role), per-request billed APIs (Cost Explorer, Pricing), and mutating calls. A few account-destructive calls are blocked outright.

## Limits

- The reviewers are heuristics, not a security audit.
- The AWS wrapper was tested with dry runs and unit tests only. It has not been run against a real AWS account.
- Terraform plan/apply, kubectl and Jenkins are not wrapped yet. Use `run_shell` (asks first) for those.
