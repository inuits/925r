from MySQLdb import _mysql
from sys import argv
import os
from minio import Minio
from minio.error import S3Error

'''
TODO:
✅ Upload attachments to minio storage, with the same file path presumably
- Change MySQL records to new URL
'''

hostname = argv[1] if len(argv) > 1 else "127.0.0.1"
port = argv[2] if len(argv) > 2 else 3307
user = argv[3] if len(argv) > 3 else "ninetofiver"
password = argv[4] if len(argv) > 4 else "ninetofiver"
media_path = argv[5] if len(argv) > 5 else "./media"
dbname = int(argv[6]) if len(argv) > 6 else "ninetofiver"
miniourl = argv[7] if len(argv) > 7 else "127.0.0.1:9000"
minio_access = argv[8] if len(argv) > 8 else "minio"
minio_secret = argv[9] if len(argv) > 9 else "minio-client" 
bucket = argv[10] if len(argv) > 10 else "media"

#* check that we have a media folder
if(not os.path.exists(os.path.abspath(media_path))):
        print(f"File path '{os.path.abspath(media_path)}' does not exist.")
        exit(1)
        
#* try connecting to db
try:
    db=_mysql.connect(hostname,user,password,dbname,port)
except error:
    print("Could not connect to MySQL database")
    print(error)
    exit(1)
    
#* try connecting to minio
client = Minio(miniourl,access_key=minio_access,secret_key=minio_secret,secure=False)


if not client.bucket_exists(bucket_name=bucket):
    print(f"Bucket '{bucket}' does not exist, creating")
    client.make_bucket(bucket)

#* grab all attachments
db.query("""SELECT * FROM ninetofiver_attachment""")
r = db.store_result()

for row in r.fetch_row(how=1,maxrows=0):
    path = row["file"].decode("utf-8")
    #* test if attachments exist in the media folder
    if not os.path.exists(os.path.join(os.path.abspath(media_path),path)):
        continue #* file is not from the media folder, skipping
    client.fput_object(bucket,path,os.path.join(os.path.abspath(media_path),path))
    print(f"Successfully added {os.path.join(os.path.abspath(media_path),path)} to bucket {bucket}")
