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

output "keycloak_url" {
  description = "Keycloak (stack=full only)"
  value       = local.full ? "http://${aws_instance.app.public_ip}:8080/" : null
}

output "airflow_url" {
  description = "Airflow UI (stack=full only)"
  value       = local.full ? "http://${aws_instance.app.public_ip}:8081/" : null
}

output "airflow_admin_password" {
  description = "Password of the Airflow UI user admin (stack=full only): terraform output -raw airflow_admin_password"
  value       = local.full ? one(random_password.airflow_admin[*].result) : null
  sensitive   = true
}
