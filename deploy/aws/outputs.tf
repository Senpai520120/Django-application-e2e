output "app_url" {
  description = "Application address"
  value       = "http://${aws_instance.app.public_ip}/"
}

output "bucket" {
  description = "Bucket holding the files"
  value       = aws_s3_bucket.files.bucket
}

output "instance_id" {
  description = "Application instance"
  value       = aws_instance.app.id
}
