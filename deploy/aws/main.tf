terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name = "users-and-roles"
  full = var.stack == "full"
  tags = {
    Project   = local.name
    ManagedBy = "terraform"
  }
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

# Airflow logins, only for the full stack.
resource "random_password" "airflow_admin" {
  count   = local.full ? 1 : 0
  length  = 24
  special = false
}

resource "random_password" "airflow_user" {
  count   = local.full ? 1 : 0
  length  = 24
  special = false
}

# ---------------------------------------------------------------------------
# S3: a private bucket for the file manager
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "files" {
  bucket        = var.bucket_name
  force_destroy = true # so terraform destroy removes the bucket with its files
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ---------------------------------------------------------------------------
# IAM: an instance role scoped to this bucket only
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "s3_access" {
  statement {
    sid       = "ListOwnBucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.files.arn]
  }

  statement {
    sid       = "ReadWriteObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.files.arn}/*"]
  }
}

resource "aws_iam_role" "app" {
  name               = "${local.name}-app"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "app_s3" {
  name   = "${local.name}-s3"
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.s3_access.json
}

resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
  tags = local.tags
}

# ---------------------------------------------------------------------------
# Network and instance
# ---------------------------------------------------------------------------

# AWS accepts a security group description in ASCII only.
# stack=app: HTTP for everyone. stack=full: the dev passwords of Keycloak and
# the demo accounts are in play, so every port is limited to admin_cidr.
resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = local.full ? "Full stack: all ports only from admin_cidr" : "HTTP for everyone, SSH only from the configured address"
  tags        = local.tags

  dynamic "ingress" {
    for_each = local.full ? {
      "Application" = 80
      "Keycloak"    = 8080
      "Airflow UI"  = 8081
    } : { "HTTP" = 80 }

    content {
      description = ingress.key
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = local.full ? [var.admin_cidr] : ["0.0.0.0/0"]
    }
  }

  dynamic "ingress" {
    for_each = var.ssh_cidr == "" ? [] : [var.ssh_cidr]

    content {
      description = "SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_instance" "app" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.app.name
  vpc_security_group_ids = [aws_security_group.app.id]
  key_name               = var.key_name == "" ? null : var.key_name

  metadata_options {
    http_tokens = "required" # IMDSv2
    # Containers sit one hop behind the host; the full stack runs the app and
    # Airflow in containers that read the instance role. null keeps the default.
    http_put_response_hop_limit = local.full ? 2 : null
  }

  # Image builds (airflow, samba, web) need more than the default disk.
  dynamic "root_block_device" {
    for_each = local.full ? [1] : []

    content {
      volume_size = 30
      volume_type = "gp3"
    }
  }

  lifecycle {
    precondition {
      condition     = !local.full || var.admin_cidr != ""
      error_message = "stack=full needs admin_cidr (your address, for example 203.0.113.7/32): all its ports are open only to it."
    }
  }

  # Changing the image changes user_data, and cloud-init only runs on the
  # first boot. Without this the instance would come back with the old
  # container.
  user_data_replace_on_change = true

  user_data = local.full ? templatefile("${path.module}/user_data_full.sh.tftpl", {
    git_ref                = var.git_ref
    repo_url               = var.repo_url
    bucket                 = aws_s3_bucket.files.bucket
    region                 = var.region
    secret_key             = random_password.secret_key.result
    airflow_password       = one(random_password.airflow_user[*].result)
    airflow_admin_password = one(random_password.airflow_admin[*].result)
    }) : templatefile("${path.module}/user_data.sh.tftpl", {
    image           = var.image
    bucket          = aws_s3_bucket.files.bucket
    region          = var.region
    secret_key      = random_password.secret_key.result
    db_password     = random_password.db_password.result
    seed_demo_users = var.seed_demo_users
  })

  tags = merge(local.tags, { Name = "${local.name}-app" })
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}
