#!/usr/bin/env python3
"""
Archive home directories onto object storage (like S3 or GCS).
Designed to be run manually, and takes care to not delete anything without a lot of
confirmation.

Original script by Yuvi Panda (@yuvipanda), 2i2c. 
https://github.com/2i2c-org/features/issues/32#issue-2221427520
"""

import hashlib
import string
import sys
import shutil
import os
import argparse
import boto3
from botocore.exceptions import ClientError
from escapism import escape
from pathlib import Path
from contextlib import contextmanager
import tempfile
import time
import subprocess
from functools import cache

@cache
def get_tar_command() -> str:
    """
    Return the tar command to use.

    We use `gnu` tar for compressing files, and Mac OS ships with bsd tar by
    default. We detect this, and tell users to get gnu tar if needed for local
    testing. Should not be an issue when running on containers.
    """

    out = subprocess.check_output(["tar", "--version"]).decode()
    if out.startswith("tar (GNU tar)"):
        return "tar"
    else:
        # We may be on Mac OS, and GNU Tar is not installed by default
        # It can be installed from homebrew with `brew install gnu-tar`,
        # which provides `gtar`
        if shutil.which("gtar"):
            return "gtar"
        else:
            print("Could not find GNU Tar on the system", file=sys.stderr)
            print(
                "If on Mac OS, please install gnu-tar with the following command (if using homebrew) and try again",
                file=sys.stderr,
            )
            print("brew install gnu-tar", file=sys.stderr)
            sys.exit(1)

def validate_homes_exist(basedir: Path, usernames: list[str], ignore_missing: bool):
    """
    Validate that all given homedirectories for users exist
    """

    errors = []

    for username in usernames:
        escaped_username = escape(
            username, safe=set(string.ascii_lowercase + string.digits), escape_char="-"
        ).lower()

    # We should still protect against directory traversal attacks
    user_home = (basedir / escaped_username).absolute()

    if basedir not in user_home.parents:
        errors.append(
            f"{user_home} refers to a directory outside of {basedir}, can not be archived"
        )

    if not user_home.exists() and not ignore_missing:
        errors.append(
            f"{username}'s home directory does not exist inside {basedir}, {user_home} not found"
        )

    if errors:
        print(
            "The following errors were found when trying to validate that all user home directories exist",
            file=sys.stderr,
        )
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)

@contextmanager
def archive_dir(dir_path: Path, archive_name: str, temp_path: str):
    """
    Archive given directory reproducibly to out_path
    """

    start_time = time.perf_counter()
    
    with tempfile.TemporaryDirectory(dir=temp_path) as d:
        target_file = Path(d) / (archive_name + ".tar.gz")
        cmd = [
            get_tar_command(),
            f"--directory={dir_path}",
            "--sort=name",
            "--numeric-owner",
            "--create",
            "--use-compress-program=pigz",
            f"--file={target_file}",
        ] + ["."]
        env = os.environ.copy()
        # Set GZip / pigz option to not write timestamp so we get consistent hashes
        env["GZIP"] = "-n"
        try:
            # Capture output and fail explicitly on non-0 error code
            # Primarily to get rid of tar: Removing leading `/' from member names
            subprocess.check_output(cmd, stderr=subprocess.STDOUT, env=env)
        except subprocess.CalledProcessError as e:
            print(f"Executing {e.cmd} failed with code {e.returncode}", file=sys.stderr)
            print(f"stdout: {e.stdout}", file=sys.stderr)
            print(f"stderr: {e.stderr}", file=sys.stderr)
            sys.exit(1)
        duration = time.perf_counter() - start_time

        file_size_gb = target_file.stat().st_size / 1024 / 1024 / 1024
        print(
            f"Tarballing {dir_path.name}  to {archive_name}.tar.gz ({file_size_gb:0.3f} GB) took {duration:0.2f}s"
        )

        yield target_file

def sha256_file(filepath: Path) -> str:

    h  = hashlib.sha256()
    b  = bytearray(128*1024)
    mv = memoryview(b)
    with open(filepath, "rb", buffering=0) as f:
        for n in iter(lambda : f.readinto(mv), 0):
            h.update(mv[:n])
    return h.hexdigest()


def archive_user(
    s3_client,
    basedir: Path,
    username: str,
    archive_name: str,
    bucket_name: str,
    prefix: str,
    ignore_missing: bool,
    delete: bool,
    temp_path: str
):

    escaped_username = escape(
        username, safe=set(string.ascii_lowercase + string.digits), escape_char="-"
    ).lower()

    homedir = basedir / username
    escaped_homedir = basedir / escaped_username

    if ignore_missing and not escaped_homedir.exists():
        print(f"User {username} does not exist, skipping archival")
        return

    print(f"Archiving {username}")
    with archive_dir(homedir, f"{escaped_username}-{archive_name}", temp_path) as archived_file:
        # Make sure the object key has the same extension as the compressed file we have
        object_name = os.path.join(prefix, username, archive_name) + "".join(
            archived_file.suffixes
        )
        sha256sum = sha256_file(archived_file)
        try:
            head_response = s3_client.head_object(Bucket=bucket_name, Key=object_name)
            # If we are here, it means that the file *does* exist
            if head_response["Metadata"].get("sha256sum") == sha256sum:
                # We have already uploaded this, and the hashes match!
                needs_upload = False
            else:
                # This file exists, *but hashes do not match!*
                # This is an error condition, and we abort so we don't overwrite user files
                print(head_response)
                print("AAAAAAAAAAA", file=sys.stderr)
                sys.exit(1)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "404":
                # Does not exist, needs to be uploaded
                needs_upload = True
            else:
                # Some other issue, let's just fail
                raise
        if needs_upload:
            start_time = time.perf_counter()
            print(f"Uploading {username}...")
            s3_client.upload_file(
                archived_file,
                bucket_name,
                object_name,
                ExtraArgs={"Metadata": {"sha256sum": sha256sum}},
            )
            duration = time.perf_counter() - start_time
            print(f"Upload for {username} complete in {duration:0.2f}s")
        else:
            if delete:
                start_time = time.perf_counter()
                print(f"Already uploaded, going to delete {username}")
                shutil.rmtree(escaped_homedir)
                duration = time.perf_counter() - start_time
                print(f"Already uploaded, deleted {username} in {duration:0.2f}s")
            else:
                print(f"Username already uploaded, skipping.")

def main():

    argparser = argparse.ArgumentParser()
    
    argparser.add_argument(
        "--archive-name",
        help="Name for user home directory in",
        required=True,
    )

    argparser.add_argument(
        "--basedir",
        help="Base directory containing user home directories",
        required=True,
    )

    argparser.add_argument(
        "--object-store",
        choices=("s3",),
        default="s3",
        help="Type of object store to upload files to",
    )

    argparser.add_argument(
        "--bucket-name",
        help="Name of object storage bucket to upload archived files to",
        required=True,
    )

    argparser.add_argument(
        "--object-prefix",
        help="Prefix to use before username when uploading archives",
        default="a/",
    )

    argparser.add_argument(
        "--usernames-file",
        help="File with list of usernames to archive, one per line",
        required=True,
    )

    argparser.add_argument(
        "--ignore-missing",
        help="Ignore missing user home directories",
        action="store_true",
    )

    argparser.add_argument(
        "--delete", 
        help="Delete home directories after uploading", 
        action="store_true"
    )

    argparser.add_argument(
        "--temp-path",
        help="Location to write the archive before uploading; default _tempdir_ uses the default tempdir.",
        default=None
    )

    args = argparser.parse_args()

    basedir = Path(args.basedir).absolute()
    usernames = []
    with open(args.usernames_file) as f:
        for line in f:
            if line.startswith("#"):
                continue
            usernames.append(line.strip())

    validate_homes_exist(basedir, usernames, args.ignore_missing)

    s3_client = boto3.client("s3")
    for username in usernames:
        archive_user(
            s3_client,
            basedir,
            username,
            args.archive_name,
            args.bucket_name,
            args.object_prefix,
            args.ignore_missing,
            args.delete,
            args.temp_path
        )

if __name__ == "__main__":
    main()
