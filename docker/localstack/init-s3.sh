#!/bin/sh
# LocalStack runs this once S3 is up (an init hook in ready.d). It keeps
# nothing between starts, so the bucket of docker-compose.s3.yml is made
# again on every start, a stop and start in Docker Desktop included.
set -e
awslocal s3 mb s3://users-and-roles-files
