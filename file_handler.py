# file_handler.py
import os
import datetime
import tarfile

def backup_ghost_files(ghost_path, backup_path):
    """
    Compresses the Ghost content directory into a tar.gz file.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"ghost_backup_{timestamp}.tar.gz"
    backup_filepath = os.path.join(backup_path, backup_filename)

    if not os.path.exists(backup_path):
        os.makedirs(backup_path)

    print(f"Backing up {ghost_path} to {backup_filepath}...")
    with tarfile.open(backup_filepath, "w:gz") as tar:
        tar.add(ghost_path, arcname=os.path.basename(ghost_path))
    
    print("Backup completed.")
    return backup_filepath

def find_images(images_path, log_path):
    """
    Finds all non-webp images, logs them, and identifies duplicates.
    """
    if not os.path.exists(images_path):
        print(f"Error: Images directory not found at {images_path}")
        return [], []

    if not os.path.exists(log_path):
        os.makedirs(log_path)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    image_list_log_path = os.path.join(log_path, f"image_list_{timestamp}.log")
    duplicate_files_log_path = os.path.join(log_path, f"duplicate_files_{timestamp}.log")

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

from PIL import Image

def convert_images_to_webp(image_paths, duplicates, quality, log_path, images_path):
    """
    Converts images to WebP format and logs the conversions.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    conversion_log_path = os.path.join(log_path, f"conversion_log_{timestamp}.log")
    conversion_map = {}

    print(f"Starting image conversion to WebP with quality={quality}...")

    with open(conversion_log_path, 'w') as log_file:
        for image_path in image_paths:
            try:
                original_basename, original_ext = os.path.splitext(os.path.basename(image_path))
                output_dir = os.path.dirname(image_path)
                
                # Handle duplicate basenames
                is_duplicate = any(image_path in path_list for path_list in duplicates.values())
                if is_duplicate:
                    new_basename = f"{original_basename}{original_ext.replace('.', '_')}"
                else:
                    new_basename = original_basename

                output_filename = f"{new_basename}.webp"
                output_path = os.path.join(output_dir, output_filename)

                # Convert image
                with Image.open(image_path) as img:
                    img.save(output_path, 'webp', quality=quality)

                # Create paths for DB replacement (e.g., /content/images/2023/10/image.png)
                relative_original = os.path.relpath(image_path, images_path)
                relative_new = os.path.relpath(output_path, images_path)
                db_path_original = os.path.join('/content/images', relative_original)
                db_path_new = os.path.join('/content/images', relative_new)

                conversion_map[db_path_original] = db_path_new
                log_file.write(f"{image_path} -> {output_path}\n")

            except Exception as e:
                error_message = f"Failed to convert {image_path}: {e}\n"
                print(error_message)
                log_file.write(error_message)

    print(f"Image conversion finished. Log saved to: {conversion_log_path}")
    return conversion_map

