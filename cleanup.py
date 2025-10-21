# cleanup.py
import os
import re
import mysql.connector
import config
import argparse
import itertools
import datetime
import tarfile
import subprocess
import multiprocessing
import tempfile

def get_used_images_from_db(db_config):
    """Scans the database to find all image paths currently in use."""
    print("Scanning database for used images...")
    used_images = set()
    image_path_regex = re.compile(r'/content/images/[A-Za-z0-9\.\-\_/]+')
    ghost_url_prefix = '__GHOST_URL__'

    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                # Scan posts table
                cursor.execute("SELECT html, feature_image FROM posts")
                posts = cursor.fetchall()
                for post in posts:
                    if post['html']:
                        used_images.update(image_path_regex.findall(post['html']))
                    if post['feature_image']:
                        feature_img_path = post['feature_image']
                        if feature_img_path.startswith(ghost_url_prefix):
                            feature_img_path = feature_img_path[len(ghost_url_prefix):]
                        if feature_img_path.startswith('/content/images/'):
                            used_images.add(feature_img_path)

                # Scan settings table
                setting_keys = ('logo', 'cover_image', 'icon')
                query_template = "SELECT `value` FROM settings WHERE `key` IN ({})"
                in_clause = ', '.join(['%s'] * len(setting_keys))
                query = query_template.format(in_clause)
                cursor.execute(query, setting_keys)
                settings = cursor.fetchall()
                for setting in settings:
                    if setting['value']:
                        setting_path = setting['value']
                        if setting_path.startswith(ghost_url_prefix):
                            setting_path = setting_path[len(ghost_url_prefix):]
                        if setting_path.startswith('/content/images/'):
                            used_images.add(setting_path)

        print(f"Found {len(used_images)} unique image paths in the database.")
        return used_images

    except mysql.connector.Error as e:
        print(f"Database error while scanning for images: {e}")
        return None

def find_unused_images(images_path, db_config, dry_run=False):
    """Compares images on disk with images used in the DB to find orphans."""
    used_db_paths = get_used_images_from_db(db_config)
    if used_db_paths is None:
        return None # Error occurred in DB scan

    print("Scanning filesystem for all images...")
    physical_files = {}
    for root, _, files in os.walk(images_path):
        for file in files:
            absolute_path = os.path.join(root, file)
            # Create a DB-style path to compare with used_db_paths
            relative_path = os.path.relpath(absolute_path, images_path)
            db_style_path = os.path.join('/content/images', relative_path)
            physical_files[db_style_path] = absolute_path
    
    print(f"Found {len(physical_files)} total image files on disk.")

    # This regex will remove /size/w.../ and /format/.../ parts of a path
    size_regex = re.compile(r'/size/w\d+')
    format_regex = re.compile(r'/format/\w+') # Handles webp and potentially others

    print("Normalizing used image paths to identify base images...\n")
    base_used_paths = set()
    for path in used_db_paths:
        # Strip both size and format to get the true base path
        # e.g., /content/images/size/w300/format/webp/2023/img.png -> /content/images/2023/img.png
        base_path = format_regex.sub('', size_regex.sub('', path.strip()))
        base_used_paths.add(base_path)
    print(f"Found {len(base_used_paths)} unique base images in use.")

    if dry_run:
        print("\n--- DRY RUN: Base Used Paths (sample) ---\n")
        for path in itertools.islice(base_used_paths, 5):
            print(f"- {path}")
        print("\n-------------------------------------\n")

    # Find unused files by checking if their base path is in the set of used base paths.
    unused_file_paths = []
    
    # Removed the entire per-file debug logging block here

    for db_style_path, absolute_path in physical_files.items():
        # Apply the same normalization to the physical file's path
        base_physical_path = format_regex.sub('', size_regex.sub('', db_style_path))
        is_used = False

        # Check 1: Is the exact base path used?
        if base_physical_path in base_used_paths:
            is_used = True
        else:
            # Check 2: Is it an _o file whose non-_o version is used?
            # Extract filename and extension
            path_dir, path_filename = os.path.split(base_physical_path)
            filename_no_ext, ext = os.path.splitext(path_filename)

            if filename_no_ext.lower().endswith('_o'):
                # Construct the path without _o
                filename_without_o = filename_no_ext[:-2] # Remove '_o'
                o_stripped_base_path = os.path.join(path_dir, filename_without_o + ext)
                
                if o_stripped_base_path in base_used_paths:
                    is_used = True
        
        if not is_used:
            unused_file_paths.append(absolute_path)

    # Removed the "--- END DRY RUN ANALYSIS ---" here

    print(f"Found {len(unused_file_paths)} unused images.")
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

def backup_and_delete_unused_images(unused_files, backup_path, log_path, database_name, dry_run=False, nobackup=False):
    """
    Logs, backs up, and deletes the list of unused files.
    If dry_run is True, only prints the files that would be deleted.
    If nobackup is True, skips the backup process.
    """
    if not unused_files:
        print("No unused files to process.")
        return

    if dry_run:
        print("\n--- DRY RUN MODE ---")
        print(f"Found {len(unused_files)} unused files.")
        print("The following files would be backed up and deleted:")
        for filepath in unused_files:
            print(f"- {filepath}")
        print("\nNo actual changes will be made.")
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Log the files to be deleted
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    log_filepath = os.path.join(log_path, f"unused_files_log_{database_name}_{timestamp}.log")
    with open(log_filepath, 'w') as f:
        for filepath in unused_files:
            f.write(f"{filepath}\n")
    print(f"List of unused files saved to: {log_filepath}")

    print("\n--- Unused Files Found ---")
    for filepath in unused_files:
        print(f"- {filepath}")
    print("--------------------------")

    # Confirm with the user before deleting
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

    # Backup the files
    if not nobackup:
        if not os.path.exists(backup_path):
            os.makedirs(backup_path)
        backup_filepath = os.path.join(backup_path, f"unused_images_backup_{database_name}_{timestamp}.tar.gz")
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

    # Delete the files
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
    database_name = config.db_config['database']
    
    unused_images = find_unused_images(config.images_path, config.db_config, dry_run=args.dry)
    
    if unused_images is not None:
        backup_and_delete_unused_images(unused_images, config.backup_path, config.log_path, database_name, dry_run=args.dry, nobackup=args.nobackup)
