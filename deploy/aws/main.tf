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
  tags = {
    Project   = local.name
    ManagedBy = "terraform"
  }
}

resource "random_password" "secret_key" {
  length  = 64
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
resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "HTTP for everyone, SSH only from the configured address"
  tags        = local.tags

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
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
  }

  # Changing the image changes user_data, and cloud-init only runs on the
  # first boot. Without this the instance would come back with the old
  # container.
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    image       = var.image
    bucket      = aws_s3_bucket.files.bucket
    region      = var.region
    secret_key  = random_password.secret_key.result
    db_password = random_password.db_password.result
  })

  tags = merge(local.tags, { Name = "${local.name}-app" })
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}
