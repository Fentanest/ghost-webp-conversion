# cleanup.py
import os
import re
import mysql.connector
import config

def get_used_images_from_db(db_config):
    """Scans the database to find all image paths currently in use."""
    print("Scanning database for used images...")
    used_images = set()
    # Regex to find all variants of /content/images/ paths
    image_path_regex = re.compile(r'/content/images/[A-Za-z0-9\.\-\_/]+')

    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT html, feature_image FROM posts")
                posts = cursor.fetchall()

                for post in posts:
                    # Scan html content
                    if post['html']:
                        found_in_html = image_path_regex.findall(post['html'])
                        used_images.update(found_in_html)
                    
                    # Scan feature_image
                    if post['feature_image']:
                        # feature_image is a direct path, no regex needed
                        used_images.add(post['feature_image'])

        print(f"Found {len(used_images)} unique image paths in the database.")
        return used_images

    except mysql.connector.Error as e:
        print(f"Database error while scanning for images: {e}")
        return None

def find_unused_images(images_path, db_config):
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

    # Find the difference
    physical_db_paths = set(physical_files.keys())
    unused_db_paths = physical_db_paths - used_db_paths

    unused_file_paths = [physical_files[path] for path in unused_db_paths]

    print(f"Found {len(unused_file_paths)} unused images.")
    return unused_file_paths

import datetime
import tarfile
import subprocess
import multiprocessing
import tempfile

def _check_pigz_installed():
    """
    Checks if pigz is installed and available in the system's PATH.
    """
    try:
        subprocess.run(['pigz', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def backup_and_delete_unused_images(unused_files, backup_path, log_path, database_name):
    """
    Logs, backs up, and deletes the list of unused files.
    """
    if not unused_files:
        print("No unused files to process.")
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
    print("The list of files to be deleted is in the log file shown above.")
    print("A backup archive will be created in the backup directory.")
    
    user_input = input("Are you sure you want to proceed? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Cleanup cancelled by user.")
        return

    # Backup the files
    if not os.path.exists(backup_path):
        os.makedirs(backup_path)
    backup_filepath = os.path.join(backup_path, f"unused_images_backup_{database_name}_{timestamp}.tar.gz")
    print(f"Backing up unused files to {backup_filepath}...")

    if _check_pigz_installed():
        print("Using pigz for parallel compression.")
        try:
            # Create a temporary file to list files for tar
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file_list:
                for fpath in unused_files:
                    temp_file_list.write(f"{fpath}\n")
            temp_file_list_path = temp_file_list.name

            # tar -T <temp_file_list> -c | pigz > <backup_filepath>
            tar_command = ['tar', '-T', temp_file_list_path, '-c']
            pigz_command = ['pigz', '-p', str(os.cpu_count() or 1)]

            tar_process = subprocess.Popen(tar_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            pigz_process = subprocess.Popen(pigz_command, stdin=tar_process.stdout, stdout=open(backup_filepath, 'wb'), stderr=subprocess.PIPE)
            tar_process.stdout.close() # Allow tar_process to receive a SIGPIPE if pigz exits

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
            # Fallback to tarfile
            with tarfile.open(backup_filepath, "w:gz") as tar:
                for filepath in unused_files:
                    tar.add(filepath, arcname=os.path.basename(filepath))
            print("Backup completed with standard tarfile.")
        finally:
            # Clean up the temporary file list
            if 'temp_file_list_path' in locals() and os.path.exists(temp_file_list_path):
                os.remove(temp_file_list_path)
    else:
        print("pigz not found, using standard tarfile for compression.")
        with tarfile.open(backup_filepath, "w:gz") as tar:
            for filepath in unused_files:
                tar.add(filepath, arcname=os.path.basename(filepath))
        print("Backup completed with standard tarfile.")

    # Delete the files
    print("Deleting unused files...")
    deleted_count = 0
    for filepath in unused_files:
        try:
            os.remove(filepath)
            deleted_count += 1
        except OSError as e:
            print(f"Error deleting file {filepath}: {e}")
    
    print(f"Successfully deleted {deleted_count} unused files.")

if __name__ == "__main__":
    print("Starting the unused image cleanup process...")
    database_name = config.db_config['database']
    unused_images = find_unused_images(config.images_path, config.db_config)
    if unused_images is not None:
        backup_and_delete_unused_images(unused_images, config.backup_path, config.log_path, database_name)
