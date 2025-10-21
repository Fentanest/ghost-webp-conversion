# file_handler.py
import os
import datetime
import tarfile
import subprocess
import multiprocessing
from PIL import Image # Moved import here

def _check_pigz_installed():
    """
    Checks if pigz is installed and available in the system's PATH.
    """
    try:
        subprocess.run(['pigz', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def backup_ghost_files(ghost_path, backup_path, database_name, nobackup=False, dry_run=False):
    """
    Compresses the Ghost content directory into a tar.gz file, using pigz if available.
    """
    if nobackup:
        print("Skipping Ghost file backup as per --nobackup option.")
        return None

    if dry_run:
        print(f"DRY RUN: Would backup Ghost files from {ghost_path} to {os.path.join(backup_path, f'ghost_backup_{database_name}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.tar.gz')}")
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"ghost_backup_{database_name}_{timestamp}.tar.gz"
    backup_filepath = os.path.join(backup_path, backup_filename)

    if not os.path.exists(backup_path):
        os.makedirs(backup_path)

    print(f"Backing up {ghost_path} to {backup_filepath}...")

    if _check_pigz_installed():
        print("Using pigz for parallel compression.")
        try:
            ghost_parent_dir = os.path.dirname(ghost_path)
            ghost_basename = os.path.basename(ghost_path)
            
            # tar -C <parent_of_ghost_path> -cf - <basename_of_ghost_path> | pigz > <backup_filepath>
            tar_command = ['tar', '-C', ghost_parent_dir, '-cf', '-', ghost_basename]
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
            return backup_filepath
        except Exception as e:
            print(f"Error using pigz, falling back to standard tarfile: {e}")
            # Fallback to tarfile
            with tarfile.open(backup_filepath, "w:gz") as tar:
                tar.add(ghost_path, arcname=os.path.basename(ghost_path))
            print("Backup completed with standard tarfile.")
            return backup_filepath
    else:
        print("pigz not found, using standard tarfile for compression.")
        with tarfile.open(backup_filepath, "w:gz") as tar:
            tar.add(ghost_path, arcname=os.path.basename(ghost_path))
        print("Backup completed with standard tarfile.")
        return backup_filepath

def find_images(images_path, log_path, database_name):
    """
    Finds all non-webp images, logs them, and identifies duplicates.
    """
    if not os.path.exists(images_path):
        print(f"Error: Images directory not found at {images_path}")
        return [], []

    if not os.path.exists(log_path):
        os.makedirs(log_path)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    image_list_log_path = os.path.join(log_path, f"image_list_{database_name}_{timestamp}.log")
    duplicate_files_log_path = os.path.join(log_path, f"duplicate_files_{database_name}_{timestamp}.log")

    all_images = []
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
    for root, _, files in os.walk(images_path):
        for file in files:
            if file.lower().endswith(image_extensions):
                all_images.append(os.path.join(root, file))

    print(f"Found {len(all_images)} images to process.")

    # Log all found images
    with open(image_list_log_path, 'w') as f:
        for image_path in all_images:
            f.write(f"{image_path}\n")
    print(f"Full list of images saved to: {image_list_log_path}")

    # Find duplicates
    basenames = {}
    for image_path in all_images:
        basename, _ = os.path.splitext(image_path)
        if basename not in basenames:
            basenames[basename] = []
        basenames[basename].append(image_path)

    duplicates = {base: paths for base, paths in basenames.items() if len(paths) > 1}

    if duplicates:
        print(f"Found {len(duplicates)} sets of files with duplicate names.")
        with open(duplicate_files_log_path, 'w') as f:
            for basename, paths in duplicates.items():
                f.write(f"Basename: {basename}\n")
                for path in paths:
                    f.write(f"  - {path}\n")
        print(f"List of duplicate-named files saved to: {duplicate_files_log_path}")
    
    return all_images, duplicates

def _convert_worker(args):
    """
    Worker function to convert a single image. To be used by a multiprocessing Pool.
    """
    image_path, duplicates, quality, images_path, dry_run = args
    try:
        original_basename, original_ext = os.path.splitext(os.path.basename(image_path))
        output_dir = os.path.dirname(image_path)
        
        is_duplicate = any(image_path in path_list for path_list in duplicates.values())
        final_basename = original_basename # Start with original basename

        # Check for _o suffix
        has_o_suffix = False
        if final_basename.lower().endswith('_o'):
            has_o_suffix = True
            # Temporarily remove _o to apply duplicate handling
            final_basename = final_basename[:-2] # Remove '_o'

        if is_duplicate:
            # Apply duplicate handling
            # The current logic appends original_ext.replace('.', '_')
            final_basename = f"{final_basename}{original_ext.replace('.', '_')}"
        
        # Re-add _o suffix if it was present
        if has_o_suffix:
            final_basename = f"{final_basename}_o"

        output_filename = f"{final_basename}.webp"
        output_path = os.path.join(output_dir, output_filename)

        if not dry_run: # Only save if not dry_run
            with Image.open(image_path) as img:
                # Ensure image is in a mode that supports saving as webp (e.g., RGB)
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                img.save(output_path, 'webp', quality=quality)
        else:
            print(f"DRY RUN: Would convert {image_path} to {output_path}") # Log dry run conversion

        relative_original = os.path.relpath(image_path, images_path)
        relative_new = os.path.relpath(output_path, images_path)
        db_path_original = os.path.join('/content/images', relative_original)
        db_path_new = os.path.join('/content/images', relative_new)

        return ('success', image_path, output_path, db_path_original, db_path_new)

    except Exception as e:
        return ('error', image_path, str(e))

def convert_images_to_webp(image_paths, duplicates, quality, log_path, images_path, database_name, dry_run=False):
    """
    Converts images to WebP format in parallel and logs the conversions.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    conversion_log_path = os.path.join(log_path, f"conversion_log_{database_name}_{timestamp}.log")
    conversion_map = {}

    # Pass dry_run to the worker function
    tasks = [(path, duplicates, quality, images_path, dry_run) for path in image_paths]

    if dry_run:
        print("DRY RUN: Image conversion process will be simulated.")
    print(f"Starting parallel image conversion for {len(image_paths)} images...")
    
    with multiprocessing.Pool() as pool:
        results = pool.map(_convert_worker, tasks)

    with open(conversion_log_path, 'w') as log_file:
        for result in results:
            if result[0] == 'success':
                _, image_path, output_path, db_path_original, db_path_new = result
                conversion_map[db_path_original] = db_path_new
                log_file.write(f"{image_path} -> {output_path}\n")
            else:
                _, image_path, error_message = result
                error_line = f"Failed to convert {image_path}: {error_message}\n"
                print(error_line.strip())
                log_file.write(error_line)

    print(f"Image conversion finished. Log saved to: {conversion_log_path}")
    return conversion_map
