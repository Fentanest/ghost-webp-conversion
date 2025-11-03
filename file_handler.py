# file_handler.py
import os
from datetime import datetime
import tarfile
import subprocess
import multiprocessing
from PIL import Image
from urllib.parse import urlparse, urlunparse, unquote

import re

def _normalize_path(path_segment):
    """Removes responsive image path segments like /size/wXXX/ and /format/webp/."""
    path_segment = re.sub(r'/size/w\d+/?', '/', path_segment)
    path_segment = re.sub(r'/format/webp/?', '/', path_segment)
    # Clean up any double slashes that might result
    path_segment = path_segment.replace('//', '/')
    return path_segment

def _process_url(url, conversion_map):
    """
    Helper function to process a single media URL, handling a map with consistent key/value types.
    """
    if not url:
        return url

    # Decode the URL first to handle encoded characters (e.g., %20 for space)
    original_url = unquote(url)
    new_url_or_path = None

    # 1. Direct lookup (for absolute URLs or relative paths if they match exactly)
    if original_url in conversion_map:
        new_url_or_path = conversion_map[original_url]
    else:
        # 2. Parse URL and look up path
        try:
            parsed_url = urlparse(original_url)
            path = parsed_url.path
        except ValueError:
            return original_url

        path_for_lookup = _normalize_path(path)

        if path_for_lookup in conversion_map:
            new_url_or_path = conversion_map[path_for_lookup]
        else:
            # 3. Handle already-webp URLs
            base, ext = os.path.splitext(path_for_lookup)
            if ext.lower() == '.webp':
                for original_ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'):
                    non_webp_path = base + original_ext
                    if non_webp_path in conversion_map:
                        new_url_or_path = conversion_map[non_webp_path]
                        break
    
    if new_url_or_path:
        # We have a new path or a new absolute URL. Handle the size prefix.
        parsed_original = urlparse(original_url)
        size_match = re.match(r'(/content/images/size/w\d+/)', parsed_original.path)

        if not size_match:
            # No size prefix, just return the direct map result
            return new_url_or_path

        # Size prefix exists, we need to inject it.
        size_prefix = size_match.group(1)

        # Check if the new value is a full URL or just a path
        if urlparse(new_url_or_path).scheme:
            # It's a full URL
            parsed_new = urlparse(new_url_or_path)
            new_path_with_size = parsed_new.path.replace('/content/images/', size_prefix, 1)
            return urlunparse(parsed_new._replace(path=new_path_with_size))
        else:
            # It's just a path
            new_path_with_size = new_url_or_path.replace('/content/images/', size_prefix, 1)
            # Reconstruct the URL using the *original* scheme/netloc but the new path
            return urlunparse(parsed_original._replace(path=new_path_with_size))

    # If no conversion found, return the original URL
    return original_url

def _check_pigz_installed():
    """
    Checks if pigz is installed and available in the system's PATH.
    """
    try:
        subprocess.run(['pigz', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def backup_ghost_files(ghost_path, backup_path, database_name, timestamp, nobackup=False, dry_run=False):
    """
    Compresses the Ghost content directory into a tar.gz file, using pigz if available.
    """
    if nobackup:
        print("Skipping Ghost file backup as per --nobackup option.")
        return None

    if dry_run:
        print(f"DRY RUN: Would backup Ghost files from {ghost_path} to {os.path.join(backup_path, f'ghost_backup_{database_name}_{timestamp}.tar.gz')}")
        return None

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
            
            tar_command = ['tar', '-C', ghost_parent_dir, '-cf', '-', ghost_basename]
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
            return backup_filepath
        except Exception as e:
            print(f"Error using pigz, falling back to standard tarfile: {e}")
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

def find_images(images_path, log_path, database_name, timestamp):
    """
    Finds all non-webp images, logs them, and identifies duplicates.
    Ignores responsive image directories.
    """
    if not os.path.exists(images_path):
        print(f"Error: Images directory not found at {images_path}")
        return [], []

    if not os.path.exists(log_path):
        os.makedirs(log_path)

    image_list_log_path = os.path.join(log_path, f"image_list_{database_name}_{timestamp}.log")
    duplicate_files_log_path = os.path.join(log_path, f"duplicate_files_{database_name}_{timestamp}.log")

    all_images = []
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff')
    ignore_dirs = ['size', 'format']

    for root, dirs, files in os.walk(images_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            if file.lower().endswith(image_extensions):
                all_images.append(os.path.join(root, file))

    print(f"Found {len(all_images)} original images to process.")

    with open(image_list_log_path, 'w') as f:
        for image_path in all_images:
            f.write(f"{image_path}\n")
    print(f"Full list of images saved to: {image_list_log_path}")

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
    If the target WebP file already exists, it finds a unique name by appending a number.
    """
    image_path, duplicates, quality, images_path, dry_run, timestamp = args
    try:
        # Exclude files without an extension or .ico files
        _, ext = os.path.splitext(image_path)
        if not ext or ext.lower() == '.ico':
            return ('skipped', image_path, 'File has no extension or is an icon file.')

        original_basename, original_ext = os.path.splitext(os.path.basename(image_path))
        output_dir = os.path.dirname(image_path)
        
        is_duplicate = any(image_path in path_list for path_list in duplicates.values())
        final_basename = original_basename

        has_o_suffix = False
        if final_basename.lower().endswith('_o'):
            has_o_suffix = True
            final_basename = final_basename[:-2]

        if is_duplicate:
            final_basename = f"{final_basename}{original_ext.replace('.', '_')}"
        
        if has_o_suffix:
            final_basename = f"{final_basename}_o"

        output_filename = f"{final_basename}.webp"
        output_path = os.path.join(output_dir, output_filename)

        if os.path.exists(output_path):
            counter = 1
            base_name_for_uniqueness = final_basename
            while os.path.exists(output_path):
                unique_basename = f"{base_name_for_uniqueness}_{counter}"
                output_filename = f"{unique_basename}.webp"
                output_path = os.path.join(output_dir, output_filename)
                counter += 1
                if counter > 100:
                    raise Exception(f"Could not find a unique filename for {image_path} after 100 attempts.")

        if not dry_run:
            with Image.open(image_path) as img:
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                img.save(output_path, 'webp', quality=quality)
        else:
            print(f"DRY RUN: Would convert {image_path} to {output_path}")

        relative_original = os.path.relpath(image_path, images_path)
        relative_new = os.path.relpath(output_path, images_path)
        
        url_path_original = os.path.join('/content/images', relative_original).replace('\\', '/')
        url_path_new = os.path.join('/content/images', relative_new).replace('\\', '/')

        return ('success', image_path, output_path, url_path_original, url_path_new)

    except Exception as e:
        return ('error', image_path, str(e), None, None)

def convert_images_to_webp(image_paths, duplicates, quality, log_path, images_path, database_name, ghost_api_url, timestamp, dry_run=False):
    """
    Converts images to WebP format in parallel and logs the conversions.
    The conversion_map now maps various URL formats to the new WebP URL path, maintaining key/value type consistency.
    """
    conversion_log_path = os.path.join(log_path, f"conversion_log_{database_name}_{timestamp}.log")
    conversion_map = {}
    api_url_base = ghost_api_url.rstrip('/')

    tasks = [(path, duplicates, quality, images_path, dry_run, timestamp) for path in image_paths]

    if dry_run:
        print("DRY RUN: Image conversion process will be simulated.")
    print(f"Starting parallel image conversion for {len(image_paths)} images...")
    
    with multiprocessing.Pool() as pool:
        results = pool.map(_convert_worker, tasks)

    with open(conversion_log_path, 'w') as log_file:
        for result in results:
            if result[0] == 'success':
                _, original_filesystem_path, new_webp_filesystem_path, url_path_original, url_path_new = result
                
                log_file.write(f"{original_filesystem_path} -> {new_webp_filesystem_path}\n")

                # Create all path/URL variations for the new WebP file
                new_absolute_url = f"{api_url_base}{url_path_new}"
                original_absolute_url = f"{api_url_base}{url_path_original}"

                # 1. Filesystem path -> new Filesystem path
                conversion_map[original_filesystem_path] = new_webp_filesystem_path
                # 2. URL path -> new URL path
                conversion_map[url_path_original] = url_path_new
                # 3. Absolute URL -> new absolute URL
                conversion_map[original_absolute_url] = new_absolute_url
            
            elif result[0] == 'skipped':
                _, image_path, reason = result
                log_file.write(f"SKIPPED: {image_path} ({reason})\n")

            else: # error
                _, image_path, error_message, _, _ = result

    print(f"Image conversion finished. Log saved to: {conversion_log_path}")
    return conversion_map
