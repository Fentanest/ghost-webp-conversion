# cleanup.py
import os
import re
import config
import argparse
import itertools
import datetime
import tarfile
import subprocess
import multiprocessing
import tempfile
import requests
import jwt
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timedelta

def generate_jwt(api_key):
    """Generates a JWT for Ghost Admin API authentication."""
    try:
        key_id, secret = api_key.split(':')
        secret_bytes = bytes.fromhex(secret)
        payload = {
            'iat': int(datetime.now().timestamp()),
            'exp': int((datetime.now() + timedelta(minutes=5)).timestamp()),
            'aud': '/admin/'
        }
        token = jwt.encode(
            payload,
            secret_bytes,
            algorithm='HS256',
            headers={'alg': 'HS256', 'typ': 'JWT', 'kid': key_id}
        )
        return token
    except Exception as e:
        print(f"Error generating JWT: {e}")
        return None

def get_used_images_from_api():
    """Scans Ghost via the Admin API to find all image paths currently in use."""
    print("Scanning Ghost API for used images...")
    used_images = set()
    # Regex to find any URL-like string pointing to content (images or media)
    url_regex = re.compile(r'''https?://[^/\s"'\)]+/content/(?:images|media)/[^\s"'\)]+''')

    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token. Please check your Admin API Key in config.py.")
        return None

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')

    try:
        with requests.Session() as s:
            s.headers.update(headers)

            # 1. Scan posts
            posts_url = f"{api_url}/ghost/api/admin/posts/?limit=all&formats=html,mobiledoc&fields=html,feature_image,mobiledoc"
            print("Fetching all posts via API...")
            response = s.get(posts_url)
            response.raise_for_status()
            posts = response.json().get('posts', [])
            
            for post in posts:
                # --- Process HTML field ---
                if post.get('html'):
                    # Use BeautifulSoup for accurate parsing of src/srcset
                    soup = BeautifulSoup(post['html'], 'html.parser')
                    for tag in soup.find_all(['img', 'video', 'audio', 'source']):
                        if tag.has_attr('src'):
                            path = urlparse(tag['src']).path
                            if path.startswith(('/content/images/', '/content/media/')):
                                used_images.add(path)
                        if tag.has_attr('srcset'):
                            for srcset_part in tag['srcset'].split(','):
                                url = srcset_part.strip().split(' ')[0]
                                path = urlparse(url).path
                                if path.startswith(('/content/images/', '/content/media/')):
                                    used_images.add(path)
                    # Also run a generic regex for anything missed (e.g., background-image)
                    missed_urls = url_regex.findall(post['html'])
                    for url in missed_urls:
                        used_images.add(urlparse(url).path)

                # --- Process mobiledoc field ---
                if post.get('mobiledoc'):
                    mobiledoc_urls = url_regex.findall(post['mobiledoc'])
                    for url in mobiledoc_urls:
                        used_images.add(urlparse(url).path)

                # --- Process feature_image ---
                if post.get('feature_image'):
                    path = urlparse(post['feature_image']).path
                    if path.startswith(('/content/images/', '/content/media/')):
                        used_images.add(path)

            # 2. Scan settings
            print("Fetching settings via API...")
            settings_url = f"{api_url}/ghost/api/admin/settings/"
            response = s.get(settings_url)
            response.raise_for_status()
            settings_data = response.json().get('settings', [])
            settings = {s['key']: s['value'] for s in settings_data}

            for key in ('logo', 'cover_image', 'icon'):
                if settings.get(key):
                    path = urlparse(settings[key]).path
                    if path.startswith(('/content/images/', '/content/media/')):
                        used_images.add(path)

        print(f"Found {len(used_images)} unique image paths in use via API.")
        return used_images

    except requests.exceptions.RequestException as e:
        print(f"API error while scanning for images: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return None

def find_unused_images(images_path, log_path, dry_run=False):
    """Compares images on disk with images used in the API to find orphans."""
    used_api_paths = get_used_images_from_api()
    if used_api_paths is None:
        return None # Error occurred in API scan

    # Save the list of used images to a file for debugging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    used_images_log_path = os.path.join(log_path, f"used_images_from_api_{timestamp}.json")
    print(f"\nSaving list of {len(used_api_paths)} used images to: {used_images_log_path}")
    with open(used_images_log_path, 'w', encoding='utf-8') as f:
        json.dump(list(used_api_paths), f, indent=2, ensure_ascii=False)

    print("\nScanning filesystem for all images...")
    physical_files = {}
    for root, _, files in os.walk(images_path):
        for file in files:
            absolute_path = os.path.join(root, file)
            relative_path = os.path.relpath(absolute_path, images_path)
            db_style_path = os.path.join('/content/images', relative_path).replace('\\', '/')
            physical_files[db_style_path] = absolute_path
    
    print(f"Found {len(physical_files)} total image files on disk.")

    size_regex = re.compile(r'/size/w\d+')
    format_regex = re.compile(r'/format/\w+')

    print("Normalizing used image paths to identify base images...\n")
    base_used_paths = set()
    for path in used_api_paths:
        base_path = format_regex.sub('', size_regex.sub('', path.strip()))
        base_used_paths.add(base_path)
    print(f"Found {len(base_used_paths)} unique base images in use.")

    if dry_run:
        print("\n--- DRY RUN: Base Used Paths (sample) ---\n")
        for path in itertools.islice(base_used_paths, 15):
            print(f"- {path}")
        print("\n-------------------------------------\n")

    unused_file_paths = []
    for db_style_path, absolute_path in physical_files.items():
        base_physical_path = format_regex.sub('', size_regex.sub('', db_style_path))
        is_used = False

        if base_physical_path in base_used_paths:
            is_used = True
        else:
            path_dir, path_filename = os.path.split(base_physical_path)
            filename_no_ext, ext = os.path.splitext(path_filename)

            if filename_no_ext.lower().endswith('_o'):
                filename_without_o = filename_no_ext[:-2]
                o_stripped_base_path = os.path.join(path_dir, filename_without_o + ext).replace('\\', '/')
                if o_stripped_base_path in base_used_paths:
                    is_used = True
        
        if not is_used:
            unused_file_paths.append(absolute_path)

    print(f"Found {len(unused_file_paths)} unused images.")

    # Save the list of unused images to a file for debugging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unused_images_log_path = os.path.join(log_path, f"unused_images_to_delete_{timestamp}.json")
    print(f"\nSaving list of {len(unused_file_paths)} unused images to: {unused_images_log_path}")
    with open(unused_images_log_path, 'w', encoding='utf-8') as f:
        json.dump(unused_file_paths, f, indent=2, ensure_ascii=False)

    return unused_file_paths

def _check_pigz_installed():
    """
    Checks if pigz is installed and available in the system's PATH.
    """
    try:
        subprocess.run(['pigz', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def backup_and_delete_unused_images(unused_files, backup_path, log_path, args):
    """
    Logs, backs up, and deletes the list of unused files.
    If dry_run is True, only prints the files that would be deleted.
    If nobackup is True, skips the backup process.
    """
    dry_run = args.dry
    nobackup = args.nobackup

    if unused_files:
        print("The following files are unused:")
        for filepath in unused_files:
            print(f"- {filepath}")
    else:
        print("No unused images found to delete.")

    print("\n--- Current Configuration & Settings ---")
    print(f"Ghost API URL: {config.ghost_api_url}")
    print(f"Ghost Images Path: {config.images_path}")
    print(f"Backup Path: {config.backup_path}")
    print(f"Log Path: {config.log_path}")
    print("---")
    print(f"Dry Run Mode: {'Yes' if dry_run else 'No'}")
    print(f"Skip Backups: {'Yes' if nobackup else 'No'}")
    print("----------------------------------------")

    if not unused_files:
        return

    if dry_run:
        print("\n--- DRY RUN MODE ---")
        print("No actual changes will be made.")
        return

    print("\n--- WARNING ---")
    print(f"You are about to delete {len(unused_files)} files.")
    if nobackup:
        print("!!! --nobackup option is active. NO BACKUP WILL BE CREATED. This action is irreversible. !!!")
    else:
        print("A backup archive will be created in the backup directory.")
    
    user_input = input("Are you sure you want to proceed? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Cleanup cancelled by user.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    log_filepath = os.path.join(log_path, f"unused_files_log_{timestamp}.log")
    with open(log_filepath, 'w') as f:
        for filepath in unused_files:
            f.write(f"{filepath}\n")
    print(f"List of unused files saved to: {log_filepath}")

    if not nobackup:
        if not os.path.exists(backup_path):
            os.makedirs(backup_path)
        backup_filepath = os.path.join(backup_path, f"unused_images_backup_{timestamp}.tar.gz")
        print(f"Backing up unused files to {backup_filepath}...")

        if _check_pigz_installed():
            print("Using pigz for parallel compression.")
            try:
                with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file_list:
                    for fpath in unused_files:
                        temp_file_list.write(f"{fpath}\n")
                temp_file_list_path = temp_file_list.name

                tar_command = ['tar', '-T', temp_file_list_path, '-c']
                pigz_command = ['pigz', '-p', str(os.cpu_count() or 1)]

                tar_process = subprocess.Popen(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                pigz_process = subprocess.Popen(pigz_command, stdin=tar_process.stdout, stdout=open(backup_filepath, 'wb'), stderr=subprocess.PIPE)
                tar_process.stdout.close()

                pigz_stderr = pigz_process.communicate()[1]
                tar_stderr = tar_process.communicate()[1]

                if pigz_process.returncode != 0:
                    print(f"Error during pigz compression: {pigz_stderr.decode()}")
                    raise subprocess.CalledProcessError(pigz_process.returncode, pigz_command, stderr=pigz_stderr)
                if tar_process.returncode != 0:
                    print(f"Error during tar archiving: {tar_stderr.decode()}")
                    raise subprocess.CalledProcessError(tar_process.returncode, tar_command, stderr=tar_stderr)

                print("Backup completed with pigz.")
            except Exception as e:
                print(f"Error using pigz, falling back to standard tarfile: {e}")
                with tarfile.open(backup_filepath, "w:gz") as tar:
                    for filepath in unused_files:
                        tar.add(filepath, arcname=os.path.basename(filepath))
                print("Backup completed with standard tarfile.")
            finally:
                if 'temp_file_list_path' in locals() and os.path.exists(temp_file_list_path):
                    os.remove(temp_file_list_path)
        else:
            print("pigz not found, using standard tarfile for compression.")
            with tarfile.open(backup_filepath, "w:gz") as tar:
                for filepath in unused_files:
                    tar.add(filepath, arcname=os.path.basename(filepath))
            print("Backup completed with standard tarfile.")
    else:
        print("\nSkipping backup as per --nobackup option.")

    print("\nDeleting unused files...")
    deleted_count = 0
    for filepath in unused_files:
        try:
            os.remove(filepath)
            deleted_count += 1
        except OSError as e:
            print(f"Error deleting file {filepath}: {e}")
    
    print(f"Successfully deleted {deleted_count} unused files.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up unused images from Ghost CMS content.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. Lists files to be deleted but does not delete them. Provides detailed logs.")
    parser.add_argument('--nobackup', action='store_true', help="Skip the backup process and delete files directly.")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No files will be deleted. ---\n")

    print("Starting the unused image cleanup process...")
    
    unused_images = find_unused_images(config.images_path, config.log_path, dry_run=args.dry)

    if unused_images is not None:
        backup_and_delete_unused_images(unused_images, config.backup_path, config.log_path, args)
