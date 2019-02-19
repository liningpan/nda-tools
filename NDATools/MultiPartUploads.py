import boto3
import botocore
import hashlib

from NDATools.TokenGenerator import *
from NDATools.Utils import *




class MultiPartsUpload:
    def __init__(self, bucket, prefix, config):
        self.bucket = bucket
        self.prefix = prefix
        self.config = config
        self.url = self.config.datamanager_api
        generator = NDATokenGenerator(self.url)
        self.token = generator.generate_token(self.config.username, self.config.password)
        self.access_key = self.token.access_key
        self.secret_key = self.token.secret_key
        self.session = self.token.session
        self.client = boto3.session.Session().client(service_name='s3')
        self.incomplete_mpu = []
        self.mpu_to_abort = {}

    def get_multipart_uploads(self):
        try:
            uploads = self.client.list_multipart_uploads(Bucket=self.bucket, Prefix=self.prefix)['Uploads']
            for u in uploads:
                if u not in self.incomplete_mpu:
                    self.incomplete_mpu.append(u)
                else:
                    self.mpu_to_abort[u['UploadId']] = u['Key']
        except KeyError:
            uploads = None

        if self.mpu_to_abort:
            self.abort_mpu()


    def abort_mpu(self):
        for upload_id, key in self.mpu_to_abort.items():
            self.client.abort_multipart_upload(
                Bucket=self.bucket, Key=key, UploadId=upload_id)


class UploadMultiParts:
    def __init__(self, upload_obj, full_file_path, bucket, prefix, config):
        self.chunk_size = 0
        self.upload_obj = upload_obj
        self.full_file_path = full_file_path
        self.upload_id = self.upload_obj['UploadId']
        self.bucket = bucket
        self.key = self.upload_obj['Key']
        filename = self.key.split(prefix+'/')
        filename = "".join(filename[1:])
        self.filename, self.file_size = self.full_file_path[filename]
        self.config= config
        self.url = self.config.datamanager_api
        generator = NDATokenGenerator(self.url)
        self.token = generator.generate_token(self.config.username, self.config.password)
        self.access_key = self.token.access_key
        self.secret_key = self.token.secret_key
        self.session = self.token.session
        self.client = boto3.session.Session().client(service_name='s3')
        self.completed_bytes = 0
        self.completed_parts = 0
        self.parts = []
        self.parts_completed = []


    def get_parts_information(self):
        self.upload_obj = self.client.list_parts(Bucket=self.bucket, Key=self.key,
                                             UploadId=self.upload_id)

        if 'Parts' in self.upload_obj:
            self.chunk_size = self.upload_obj['Parts'][0]['Size'] # size of first part should be size of all subsequent parts
            for p in self.upload_obj['Parts']:
                try:
                    self.parts.append({"PartNumber": p['PartNumber'], "ETag": p["ETag"]})
                    self.parts_completed.append(p["PartNumber"])
                except KeyError:
                    pass

        self.completed_bytes = self.chunk_size * len(self.parts)


    def check_md5(self, part, data):

        ETag = (part["ETag"]).split('"')[1]

        md5 = hashlib.md5(data).hexdigest()
        if md5 != ETag:
            message = "The file seems to be modified since previous upload attempt(md5 value does not match)."
            exit_client(signal=signal.SIGTERM, message=message) # force exit because file has been modified (data integrity)

    def upload_part(self, data, i):
        part = self.client.upload_part(Body=data, Bucket=self.bucket, Key=self.key, UploadId=self.upload_id, PartNumber=i)
        self.parts.append({"PartNumber": i, "ETag": part["ETag"]})
        self.completed_bytes += len(data)


    def complete(self):
        self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=self.key,
            UploadId=self.upload_id,
            MultipartUpload={"Parts": self.parts})
        print('finished uploading all parts!')


