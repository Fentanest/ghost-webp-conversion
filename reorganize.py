# reorganize.py
import os
import re
import mysql.connector
import config
from db_handler import verify_db_connection_or_abort
import argparse
import datetime
from bs4 import BeautifulSoup
import multiprocessing

def get_posts_with_images(db_config):
    """Fetches posts that contain image links in their HTML content."""
    print("Fetching posts with images from the database...")
    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = """
                SELECT id, slug, html FROM posts 
                WHERE html LIKE '%%<img%%'
                """
                cursor.execute(query)
                posts = cursor.fetchall()
                print(f"Found {len(posts)} posts with images.")
                return posts
    except mysql.connector.Error as e:
        print(f"Database error while fetching posts: {e}")
        return None

def _reorganize_worker(args):
    image_path, slug, index, images_path, dry_run = args
    try:
        original_basename, original_ext = os.path.splitext(os.path.basename(image_path))
        new_dir = os.path.join(images_path, slug)
        
        suffix = ""
        if original_basename.lower().endswith('_o'):
            suffix = "_o"

        new_filename = f"{slug}-{index + 1}{suffix}{original_ext}"
        new_path = os.path.join(new_dir, new_filename)

        if not dry_run:
            os.makedirs(new_dir, exist_ok=True)
            os.rename(image_path, new_path)
        else:
            print(f"DRY RUN: Would move {image_path} to {new_path}")

        # After moving the original, find and delete its old responsive versions
        if not dry_run:
            original_filename = os.path.basename(image_path)
            content_path = os.path.dirname(images_path)
            size_path = os.path.join(content_path, 'size')
            if os.path.exists(size_path):
                for root, _, files in os.walk(size_path):
                    if original_filename in files:
                        old_responsive_path = os.path.join(root, original_filename)
                        try:
                            os.remove(old_responsive_path)
                            print(f"Deleted old responsive image: {old_responsive_path}")
                        except OSError as e:
                            print(f"Error deleting old responsive image {old_responsive_path}: {e}")

        relative_original = os.path.relpath(image_path, images_path)
        relative_new = os.path.relpath(new_path, images_path)
        db_path_original = os.path.join('/content/images', relative_original)
        db_path_new = os.path.join('/content/images', relative_new)

        return ('success', db_path_original, db_path_new)
    except Exception as e:
        return ('error', image_path, str(e))

def reorganize_images(posts, images_path, log_path, database_name, dry_run=False):
    """Reorganizes images based on post slug."""
    print("Reorganizing images...")
    conversion_map = {}
    tasks = []
    globally_processed_images = set()

    # Sort posts by ID to have a deterministic order (usually corresponds to creation date)
    posts.sort(key=lambda p: p['id'])

    for post in posts:
        slug = post['slug']
        soup = BeautifulSoup(post['html'], 'html.parser')
        
        post_image_counter = 0
        ordered_urls = []
        for img in soup.find_all('img'):
            if img.get('src'):
                ordered_urls.append(img['src'])
            if img.get('srcset'):
                for s in img['srcset'].split(','):
                    url = s.strip().split(' ')[0]
                    if url:
                        ordered_urls.append(url)
        
        post_originals_in_order = []
        size_regex = re.compile(r'(/content/images/size/w\d+/)')
        for url in ordered_urls:
            # url_for_lookup is the path to the original image, without /size/w.../
            url_for_lookup = url
            size_match = re.match(size_regex, url)
            if size_match:
                size_prefix = size_match.group(1)
                url_for_lookup = url.replace(size_prefix, '/content/images/', 1)

            if url_for_lookup.startswith('/content/images/'):
                relative_path = url_for_lookup[len('/content/images/'):]
                image_path = os.path.join(images_path, relative_path)
                if os.path.exists(image_path) and image_path not in post_originals_in_order:
                    post_originals_in_order.append(image_path)

        for image_path in post_originals_in_order:
            if image_path not in globally_processed_images:
                tasks.append((image_path, slug, post_image_counter, images_path, dry_run))
                globally_processed_images.add(image_path)
                post_image_counter += 1

    if dry_run:
        print("DRY RUN: Image reorganization will be simulated.")
    
    print(f"Starting parallel image reorganization for {len(tasks)} images...")
    with multiprocessing.Pool() as pool:
        results = pool.map(_reorganize_worker, tasks)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filepath = os.path.join(log_path, f"reorganize_log_{database_name}_{timestamp}.log")
    
    with open(log_filepath, 'w') as log_file:
        for result in results:
            if result[0] == 'success':
                _, db_path_original, db_path_new = result
                conversion_map[db_path_original] = db_path_new
                log_file.write(f"{db_path_original} -> {db_path_new}\n")
            else:
                _, image_path, error_message = result
                error_line = f"Failed to reorganize {image_path}: {error_message}\n"
                print(error_line.strip())
                log_file.write(error_line)

    print(f"Image reorganization finished. Log saved to: {log_filepath}")
    return conversion_map

def _process_image_url(url, conversion_map):
    """
    Helper function to process a single image URL, looking it up in the conversion_map
    and reconstructing it with original prefixes.
    """
    if not url:
        return url

    original_url = url
    ghost_url_prefix = ''
    size_prefix = ''

    # Check for __GHOST_URL__ prefix
    if original_url.startswith('__GHOST_URL__'):
        ghost_url_prefix = '__GHOST_URL__'
        url = original_url.replace('__GHOST_URL__', '', 1)

    # Check for /size/wXXX/ prefix
    size_match = re.match(r'(/content/images/size/w\d+/)', url)
    if size_match:
        size_prefix = size_match.group(1)
        url_for_map_lookup = url.replace(size_prefix, '/content/images/', 1)
    else:
        url_for_map_lookup = url

    map_key = url_for_map_lookup

    if map_key in conversion_map:
        new_map_value = conversion_map[map_key]
        if size_prefix:
            new_url_path = new_map_value.replace('/content/images/', size_prefix, 1)
        else:
            new_url_path = new_map_value
        
        return f"{ghost_url_prefix}{new_url_path}"
    return original_url

def update_database_links(db_config, conversion_map, dry_run=False):
    """Updates image links in the database."""
    if not conversion_map:
        print("No image links to update.")
        return

    print("Updating database links...")
    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT id, html, feature_image FROM posts")
                posts = cursor.fetchall()

                for post in posts:
                    original_html = post['html']
                    original_feature_image = post['feature_image']
                    new_html = original_html
                    new_feature_image = original_feature_image
                    
                    html_changed = False
                    feature_image_changed = False

                    if original_html:
                        soup = BeautifulSoup(original_html, 'html.parser')
                        for img_tag in soup.find_all('img'):
                            if 'src' in img_tag.attrs:
                                old_src = img_tag['src']
                                new_src = _process_image_url(old_src, conversion_map)
                                if new_src != old_src:
                                    img_tag['src'] = new_src
                                    html_changed = True
                            
                            if 'srcset' in img_tag.attrs:
                                old_srcset = img_tag['srcset']
                                srcset_parts = old_srcset.split(',')
                                new_srcset_parts = []
                                for part in srcset_parts:
                                    part = part.strip()
                                    if not part: continue
                                    
                                    url_descriptor = part.rsplit(' ', 1)
                                    url = url_descriptor[0]
                                    descriptor = url_descriptor[1] if len(url_descriptor) > 1 else ''

                                    new_url = _process_image_url(url, conversion_map)
                                    
                                    new_srcset_parts.append(f"{new_url} {descriptor}" if descriptor else new_url)
                                
                                new_srcset = ", ".join(new_srcset_parts)
                                if new_srcset != old_srcset:
                                    img_tag['srcset'] = new_srcset
                                    html_changed = True
                        
                        if html_changed:
                            new_html = str(soup)

                    if original_feature_image:
                        new_feature_image = _process_image_url(original_feature_image, conversion_map)
                        if new_feature_image != original_feature_image:
                            feature_image_changed = True

                    if html_changed or feature_image_changed:
                        if not dry_run:
                            update_query = "UPDATE posts SET html = %s, feature_image = %s WHERE id = %s"
                            cursor.execute(update_query, (new_html, new_feature_image, post['id']))
                        else:
                            print(f"DRY RUN: Would update post ID {post['id']}")

                if not dry_run:
                    conn.commit()
                    print("Database links updated successfully.")
                else:
                    print("DRY RUN: Database link update simulated.")

    except mysql.connector.Error as e:
        print(f"Database error during link update: {e}")

def restore_from_log(log_file, images_path, db_config, dry_run=False):
    """Restores images from a reorganization log file."""
    print(f"Restoring from log file: {log_file}")
    reverse_conversion_map = {}

    with open(log_file, 'r') as f:
        for line in f:
            if '->' in line:
                original_db_path, new_db_path = [p.strip() for p in line.split('->')]
                reverse_conversion_map[new_db_path] = original_db_path

                # Convert DB paths to absolute file paths for moving
                original_relative_path = original_db_path[len('/content/images/'):]
                new_relative_path = new_db_path[len('/content/images/'):]
                original_abs_path = os.path.join(images_path, original_relative_path)
                new_abs_path = os.path.join(images_path, new_relative_path)

                if not dry_run:
                    # Ensure parent directory of original path exists
                    os.makedirs(os.path.dirname(original_abs_path), exist_ok=True)
                    if os.path.exists(new_abs_path):
                        os.rename(new_abs_path, original_abs_path)
                else:
                    print(f"DRY RUN: Would move {new_abs_path} back to {original_abs_path}")

    print("File restoration complete. Now updating database links...")
    update_database_links(db_config, reverse_conversion_map, dry_run)

def analyze_reorganization(posts, images_path, log_path, database_name):
    """Analyzes the reorganization plan and creates a detailed log."""
    print("Analyzing reorganization plan...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    analysis_log_path = os.path.join(log_path, f"reorganize_analysis_{database_name}_{timestamp}.log")
    
    globally_processed_images = set()
    tasks = []
    conversion_map = {}

    with open(analysis_log_path, 'w') as log_file:
        log_file.write("--- Image Reorganization Analysis ---\n\n")
        
        posts.sort(key=lambda p: p['id'])

        for post in posts:
            log_file.write(f"--- Post: {post['slug']} (ID: {post['id']}) ---\n")
            
            soup = BeautifulSoup(post['html'], 'html.parser')
            post_image_counter = 0
            
            ordered_urls = []
            for img in soup.find_all('img'):
                src = img.get('src', '').replace('__GHOST_URL__', '')
                if src:
                    ordered_urls.append(src)
                
                srcset = img.get('srcset', '')
                if srcset:
                    for s in srcset.split(','):
                        url = s.strip().split(' ')[0]
                        if url:
                            ordered_urls.append(url.replace('__GHOST_URL__', ''))

            post_originals_in_order = []
            size_prefix_regex = re.compile(r'/size/w\d+')
            for url in ordered_urls:
                base_url = size_prefix_regex.sub('', url).lstrip('/')
                
                if base_url.startswith('content/images/'):
                    relative_path = base_url[len('content/images/'):]
                    image_path = os.path.join(images_path, relative_path)
                    
                    if os.path.exists(image_path) and image_path not in post_originals_in_order:
                        post_originals_in_order.append(image_path)

            if not post_originals_in_order:
                log_file.write("No valid, existing images found in this post.\n\n")
                continue

            for image_path in post_originals_in_order:
                if image_path in globally_processed_images:
                    log_file.write(f"[SKIPPED] Original Path: {image_path} (already processed in another post)\n")
                    continue
                
                globally_processed_images.add(image_path)
                
                original_basename, original_ext = os.path.splitext(os.path.basename(image_path))
                suffix = "_o" if original_basename.lower().endswith('_o') else ""
                new_filename = f"{post['slug']}-{post_image_counter + 1}{suffix}{original_ext}"
                new_path = os.path.join(images_path, post['slug'], new_filename)
                
                log_file.write(f"  Image Index: {post_image_counter}\n")
                log_file.write(f"    - Original Path: {image_path}\n")
                log_file.write(f"    - New Path     : {new_path}\n")

                # For later processing
                tasks.append((image_path, post['slug'], post_image_counter, images_path, False)) # dry_run is False here, controlled later
                
                # Build conversion map for DB update analysis
                relative_original = os.path.relpath(image_path, images_path)
                relative_new = os.path.relpath(new_path, images_path)
                db_path_original = os.path.join('/content/images', relative_original)
                db_path_new = os.path.join('/content/images', relative_new)
                conversion_map[db_path_original] = db_path_new

                post_image_counter += 1
            log_file.write("\n")

        # --- DB Update Analysis ---
        log_file.write("--- Database Update Analysis ---\n")
        for original, new in conversion_map.items():
            log_file.write(f"{original} -> {new}\n")

    print(f"Analysis complete. Detailed plan saved to: {analysis_log_path}")
    return analysis_log_path, tasks, conversion_map

def main():
    parser = argparse.ArgumentParser(description="Reorganize Ghost CMS images based on post slugs.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode.")
    parser.add_argument('--restore', type=str, help="Path to a log file to restore from.")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No actual changes will be made. ---\n")

    verify_db_connection_or_abort(config.db_config)
    
    if args.restore:
        restore_from_log(args.restore, config.images_path, config.db_config, args.dry)
        print("\nProcess finished.")
        return

    # --- Analysis Phase ---
    posts = get_posts_with_images(config.db_config)
    if not posts:
        print("No posts with images found to analyze.")
        return

    analysis_log_path, tasks, conversion_map = analyze_reorganization(
        posts, config.images_path, config.log_path, config.db_config['database']
    )

    print("\n--- Current Configuration & Settings ---")
    print(f"Database Host: {config.db_config.get('host', 'N/A')}")
    print(f"Database Name: {config.db_config.get('database', 'N/A')}")
    print(f"Images Path: {config.images_path}")
    print("----------------------------------------")

    user_input = input("Do you want to proceed with reorganization based on the analysis? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Process aborted by user.")
        return

    # --- Execution Phase ---
    if not tasks:
        print("No images to reorganize.")
    else:
        print(f"Starting parallel image reorganization for {len(tasks)} images...")
        # Set dry_run for the worker tasks
        worker_tasks = [(t[0], t[1], t[2], t[3], args.dry) for t in tasks]
        with multiprocessing.Pool() as pool:
            results = pool.map(_reorganize_worker, worker_tasks)
        
        # Log the actual results
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        exec_log_path = os.path.join(config.log_path, f"reorganize_exec_{config.db_config['database']}_{timestamp}.log")
        with open(exec_log_path, 'w') as log_file:
            for result in results:
                if result[0] == 'success':
                    _, db_path_original, db_path_new = result
                    log_file.write(f"{db_path_original} -> {db_path_new}\n")
                else:
                    _, image_path, error_message = result
                    error_line = f"Failed to reorganize {image_path}: {error_message}\n"
                    print(error_line.strip())
                    log_file.write(error_line)
        print(f"Execution finished. Log saved to: {exec_log_path}")

        # Update database
        update_database_links(config.db_config, conversion_map, args.dry)

    print("\nProcess finished.")

if __name__ == "__main__":
    main()
