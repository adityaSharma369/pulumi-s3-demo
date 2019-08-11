import boto3
import logging
import os
import tarfile
import tempfile
import shutil
import subprocess
import time

def handler(event, context):
    print(event)

    # Determine the action type.
    action = event['Action']
    if action not in [ 'Create', 'Update', 'Delete' ]:
        raise Exception('Unknown action type {}'.format(action))

    # Get the object bucket/key to expand.
    bucket = event['Bucket']
    archive_key = event['ArchiveKey']
    object_acl = event.get('ObjectAcl')

    # Perform the desired S3 action.
    if action in [ 'Create', 'Update' ]:
        s3 = boto3.resource('s3')

        # Ensure we can access the bucket and object. The IAM attachment is eventually consistent, so there
        # might be a delay... wait for up to a minute before giving up.
        for i in range(60):
            try:
                s3.head_object(Bucket=bucket, Key=archive_key)
            except:
                time.sleep(1)
                continue
            break

        # Copy the archive tgz from the bucket to the local disk.
        tmp_archive = tempfile.mktemp(suffix='.tgz')
        print('| Downloading S3 archive {}/{} to {}...'.format(bucket, archive_key, tmp_archive))
        s3.meta.client.download_file(bucket, archive_key, tmp_archive)
        print('| Done.')

        try:
            # Now uncompress the entire archive.
            tmp_archive_dir = tempfile.mkdtemp()
            print('| Decompressing archive to {}...'.format(tmp_archive_dir))
            tarfile.open(tmp_archive).extractall(path=tmp_archive_dir)
            print('| Done.')

            try:
                # Run an "AWS S3 sync" command to efficiently decompress the contents. Note that because
                # we pass the --delete option, the archive itself will also be removed automatically.
                print('| Running AWS CLI to sync to {}...'.format(bucket))
                sync_args = ['s3', 'sync', tmp_archive_dir, 's3://{}'.format(bucket), '--delete']
                if object_acl:
                    print('| - Setting object ACLs to {}'.format(object_acl))
                    sync_args.append('--acl')
                    sync_args.append(object_acl)
                aws(*sync_args)
            finally:
                shutil.rmtree(tmp_archive_dir)
        finally:
            os.remove(tmp_archive)
    else:
        # Recursively delete the entire bucket so that it isn't blocked from being deleted itself.
        print('| Running AWS CLI to delete entire bucket {} ...'.format(bucket))
        aws('s3', 'rm', bucket, '--recursive')

    print('| Done.')

def aws(*args):
    print('AWS: {}'.format(' '.join(args)))
    curr_dir = os.path.dirname(os.path.realpath(__file__))
    aws_cli_path = os.path.join(curr_dir, 'aws')
    subprocess.check_output(['python3', aws_cli_path] + list(args))
