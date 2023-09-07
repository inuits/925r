# Script to migrate attachments stored on local storage to a minio bucket
Make sure to install dev dependencies (`pipenv sync -d`)

Run with `pipenv run python ./migration.py mysql_hostname mysql_port mysql_user mysql_pass path_to_current_media_folder mysql_db_name minio_hostname_and_port minio_access_key minio_secret_key minio_bucket_name`
