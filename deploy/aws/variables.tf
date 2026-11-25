variable "region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "bucket_name" {
  description = "S3 bucket name for the files (must be globally unique)"
  type        = string
}

variable "instance_type" {
  description = "Instance type. t3.micro (1 GB) is enough for stack=app only; stack=full needs m7i-flex.large (2 vCPU, 8 GB)"
  type        = string
  default     = "t3.micro"
}

variable "image" {
  description = "Application Docker image published by CI"
  type        = string
  default     = "ghcr.io/senpai520120/django-application-e2e:latest"
}

variable "ssh_cidr" {
  description = "Address allowed to reach SSH. Empty closes the port entirely"
  type        = string
  default     = ""
}

variable "key_name" {
  description = "SSH key name in AWS. Empty means no key"
  type        = string
  default     = ""
}

variable "seed_demo_users" {
  description = "Create the demo_* accounts with their published password. Only for a short-lived demo: the stand is reachable from the internet over plain HTTP"
  type        = bool
  default     = false
}

variable "stack" {
  description = "app: web + Postgres from the GHCR image (default). full: the whole stack built from git (app, S3, Airflow/DuckDB, Keycloak SSO, Samba AD)"
  type        = string
  default     = "app"

  validation {
    condition     = contains(["app", "full"], var.stack)
    error_message = "stack must be \"app\" or \"full\"."
  }
}

variable "admin_cidr" {
  description = "Your address as x.x.x.x/32. Required for stack=full: all its ports (80, 8080, 8081) are open only to it"
  type        = string
  default     = ""

  validation {
    condition     = var.admin_cidr == "" || can(cidrhost(var.admin_cidr, 0))
    error_message = "admin_cidr must be a CIDR such as 203.0.113.7/32."
  }
}

variable "git_ref" {
  description = "Branch or tag of the repository that stack=full builds from"
  type        = string
  default     = "main"
}

variable "repo_url" {
  description = "Public repository that stack=full clones"
  type        = string
  default     = "https://github.com/Senpai520120/Django-application-e2e"
}
