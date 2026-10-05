variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "nextstep"
}

variable "instance_type" {
  description = "EC2 instance type. t3.medium (4 GB) works with the 4 GB swap the bootstrap adds; t3.large builds faster."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_size" {
  description = "Root disk size in GB (Docker images + database + uploaded files)"
  type        = number
  default     = 30
}

variable "repo_url" {
  description = "HTTPS URL of the Git repository to deploy (must be cloneable without credentials)"
  type        = string
}

variable "repo_branch" {
  description = "Branch to deploy"
  type        = string
  default     = "main"
}

variable "env_file" {
  description = "Path to the production .env file. Stored encrypted in SSM Parameter Store, never in user data."
  type        = string
  default     = ".env.prod"
}

variable "domain_name" {
  description = "Optional domain (e.g. app.example.com). If set, Caddy serves HTTPS with a Let's Encrypt certificate; point an A record to the Elastic IP. If empty, the app is served over plain HTTP on the IP."
  type        = string
  default     = ""
}

variable "letsencrypt_email" {
  description = "Optional email for Let's Encrypt expiry notices (only used with domain_name)"
  type        = string
  default     = ""
}

variable "ssh_ingress_cidrs" {
  description = "CIDRs allowed to SSH (port 22). Empty = SSH closed; use SSM Session Manager instead."
  type        = list(string)
  default     = []
}

variable "key_name" {
  description = "Optional EC2 key pair name for SSH (only useful with ssh_ingress_cidrs)"
  type        = string
  default     = null
}

variable "github_repo" {
  description = "GitHub repository (owner/repo) allowed to deploy via OIDC. Must match the repository that runs deploy-ec2.yml, otherwise the trust policy denies AssumeRoleWithWebIdentity."
  type        = string
  default     = "said101112/Next-Step"
}

variable "create_oidc_provider" {
  description = "Whether to create the GitHub OIDC provider (set to false if already created in the AWS account)"
  type        = bool
  default     = true
}
