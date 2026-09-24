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
  description = "Instance type. t3.micro is inside the free tier"
  type        = string
  default     = "t3.micro"
}

variable "image" {
  description = "Application Docker image published by CI"
  type        = string
  default     = "ghcr.io/senpai520120/django_application:latest"
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
