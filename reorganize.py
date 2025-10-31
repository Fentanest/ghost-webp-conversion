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
from file_handler import _process_url # Import _process_url from file_handler

def get_posts_with_media(db_config):
    """Fetches posts that contain image, video, or audio links in their HTML content, or have a feature image."""
    print("Fetching posts with media from the database...")
    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = """
                SELECT id, slug, html, feature_image FROM posts 
                WHERE html LIKE '%%<img%%' OR html LIKE '%%<video%%' OR html LIKE '%%<audio%%' OR feature_image IS NOT NULL
                """
                cursor.execute(query)
                posts = cursor.fetchall()
                print(f"Found {len(posts)} posts with media.")
                return posts
    except mysql.connector.Error as e:
        print(f"Database error while fetching posts: {e}")
        return None

def _reorganize_worker(args):
    file_path, slug, new_filename_base, base_path, content_path_name, dry_run = args
    try:
        _, original_ext = os.path.splitext(os.path.basename(file_path))
        new_dir = os.path.join(base_path, slug)
        
        new_filename = f"{new_filename_base}{original_ext}"
        new_path = os.path.join(new_dir, new_filename)

        if not dry_run:
            os.makedirs(new_dir, exist_ok=True)
            if os.path.abspath(file_path) != os.path.abspath(new_path):
                os.rename(file_path, new_path)
        else:
            if os.path.abspath(file_path) != os.path.abspath(new_path):
                print(f"DRY RUN: Would move {file_path} to {new_path}")
            else:
                print(f"DRY RUN: Path is the same, no move needed for {file_path}")


        # This part is image-specific, should only run for images
        if not dry_run and content_path_name == 'images':
            original_filename = os.path.basename(file_path)
            content_path = os.path.dirname(base_path)
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

        relative_original = os.path.relpath(file_path, base_path)
        relative_new = os.path.relpath(new_path, base_path)
        db_path_original = os.path.join(f'/content/{content_path_name}', relative_original)
        db_path_new = os.path.join(f'/content/{content_path_name}', relative_new)

        return ('success', db_path_original, db_path_new)
    except Exception as e:
        return ('error', file_path, str(e))

def _process_url(url, conversion_map):
    """
    Helper function to process a single media URL, looking it up in the conversion_map
    and reconstructing it with original prefixes and schemes.
    """
    if not url:
        return url

    original_url = url
    ghost_url_prefix = ''
    
    if original_url.startswith('__GHOST_URL__'):
        ghost_url_prefix = '__GHOST_URL__'
        url = original_url.replace('__GHOST_URL__', '', 1)

    parsed_url = urlparse(url)
    path = parsed_url.path
    
    content_path_name = 'images' # Default
    if path.startswith('/content/media/'):
        content_path_name = 'media'

    size_prefix = ''
    url_for_map_lookup = path

    if content_path_name == 'images':
        size_match = re.match(r'(/content/images/size/w\d+/)', path)
        if size_match:
            size_prefix = size_match.group(1)
            url_for_map_lookup = path.replace(size_prefix, '/content/images/', 1)

    if url_for_map_lookup in conversion_map:
        new_path = conversion_map[url_for_map_lookup]
        if size_prefix:
            new_path = new_path.replace('/content/images/', size_prefix, 1)
        
        # Reconstruct the original URL with the new path, preserving scheme, netloc, etc.
        new_parsed_url = parsed_url._replace(path=new_path)
        new_url_string = urlunparse(new_parsed_url)
        
        return f"{ghost_url_prefix}{new_url_string}"
        
    return original_url

def update_database_links(db_config, conversion_map, dry_run=False):
    """Updates image and media links in the database."""
    if not conversion_map:
        print("No media links to update.")
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
                        
                        # Update <img> tags
                        for img_tag in soup.find_all('img'):
                            if 'src' in img_tag.attrs:
                                old_src = img_tag['src']
                                new_src = _process_url(old_src, conversion_map, config.images_path, config.media_path)
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

                                    new_url = _process_url(url, conversion_map, config.images_path, config.media_path)
                                    new_srcset_parts.append(f"{new_url} {descriptor}" if descriptor else new_url)
                                
                                new_srcset = ", ".join(new_srcset_parts)
                                if new_srcset != old_srcset:
                                    img_tag['srcset'] = new_srcset
                                    html_changed = True

                        # Update <video> and <audio> tags
                        for media_tag in soup.find_all(['video', 'audio']):
                            if 'src' in media_tag.attrs:
                                old_src = media_tag['src']
                                new_src = _process_url(old_src, conversion_map, config.images_path, config.media_path)
                                if new_src != old_src:
                                    media_tag['src'] = new_src
                                    html_changed = True
                            # Also check for <source> children
                            for source_tag in media_tag.find_all('source'):
                                if 'src' in source_tag.attrs:
                                    old_src = source_tag['src']
                                    new_src = _process_url(old_src, conversion_map, config.images_path, config.media_path)
                                    if new_src != old_src:
                                        source_tag['src'] = new_src
                                        html_changed = True
                        
                        if html_changed:
                            new_html = str(soup)

                    if original_feature_image:
                        new_feature_image = _process_url(original_feature_image, conversion_map, config.images_path, config.media_path)
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

def restore_from_log(log_file, images_path, media_path, db_config, dry_run=False):
    """Restores images and media from a reorganization log file."""
    print(f"Restoring from log file: {log_file}")
    reverse_conversion_map = {}

    with open(log_file, 'r') as f:
        for line in f:
            if '->' in line:
                original_db_path, new_db_path = [p.strip() for p in line.split('->')]
                reverse_conversion_map[new_db_path] = original_db_path

                # Determine if it's an image or media file
                if '/content/images/' in original_db_path:
                    base_path = images_path
                    content_path_name = 'images'
                elif '/content/media/' in original_db_path:
                    base_path = media_path
                    content_path_name = 'media'
                else:
                    continue

                original_relative_path = original_db_path[len(f'/content/{content_path_name}/'):]
                new_relative_path = new_db_path[len(f'/content/{content_path_name}/'):]
                original_abs_path = os.path.join(base_path, original_relative_path)
                new_abs_path = os.path.join(base_path, new_relative_path)

                if not dry_run:
                    os.makedirs(os.path.dirname(original_abs_path), exist_ok=True)
                    if os.path.exists(new_abs_path):
                        os.rename(new_abs_path, original_abs_path)
                else:
                    print(f"DRY RUN: Would move {new_abs_path} back to {original_abs_path}")

    print("File restoration complete. Now updating database links...")
    update_database_links(db_config, reverse_conversion_map, dry_run)

def analyze_reorganization(posts, images_path, media_path, log_path, database_name):
    """Analyzes the reorganization plan for all media and creates a detailed log."""
    print("Analyzing reorganization plan...")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    analysis_log_path = os.path.join(log_path, f"reorganize_analysis_{database_name}_{timestamp}.log")
    
    globally_processed_files = set()
    image_tasks = []
    media_tasks = []
    conversion_map = {}

    with open(analysis_log_path, 'w') as log_file:
        log_file.write("--- Media Reorganization Analysis ---\n\n")
        
        posts.sort(key=lambda p: p['id'])

        for post in posts:
            slug = post['slug']
            log_file.write(f"--- Post: {slug} (ID: {post['id']}) ---\n")
            
            soup = BeautifulSoup(post['html'] or '', 'html.parser')
            
            # --- 1. Feature Image ---
            if post.get('feature_image'):
                url = post['feature_image'].replace('__GHOST_URL__', '')
                path = urlparse(url).path
                
                if path.startswith('/content/images/'):
                    relative_path = path[len('/content/images/'):]
                    file_path = os.path.join(images_path, relative_path)
                    
                    if os.path.exists(file_path) and file_path not in globally_processed_files:
                        globally_processed_files.add(file_path)
                        new_filename_base = "feature_image"
                        
                        log_file.write(f"  [Feature Image]\n")
                        log_file.write(f"    - Original Path: {file_path}\n")
                        
                        _, original_ext = os.path.splitext(os.path.basename(file_path))
                        new_path = os.path.join(images_path, slug, f"{new_filename_base}{original_ext}")
                        log_file.write(f"    - New Path     : {new_path}\n")

                        image_tasks.append((file_path, slug, new_filename_base, images_path, 'images', False))
                        
                        relative_original = os.path.relpath(file_path, images_path)
                        relative_new = os.path.relpath(new_path, images_path)
                        conversion_map[os.path.join('/content/images', relative_original)] = os.path.join('/content/images', relative_new)
                    elif file_path in globally_processed_files:
                         log_file.write(f"  [Feature Image SKIPPED] Path: {file_path} (already processed)\n")

            # --- 2. Content Images ---
            post_image_counter = 0
            img_urls = []
            for img in soup.find_all('img'):
                if img.get('src'): img_urls.append(img['src'])
                if img.get('srcset'):
                    img_urls.extend([s.strip().split(' ')[0] for s in img['srcset'].split(',') if s.strip()])
            
            post_originals_in_order = []
            size_regex = re.compile(r'/size/w\d+/')
            for url in img_urls:
                url = url.replace('__GHOST_URL__', '')
                path = urlparse(url).path
                base_path = size_regex.sub('/', path).replace('//', '/')

                if base_path.startswith('/content/images/'):
                    relative_path = base_path[len('/content/images/'):]
                    file_path = os.path.join(images_path, relative_path)
                    if os.path.exists(file_path) and file_path not in post_originals_in_order:
                        post_originals_in_order.append(file_path)

            for file_path in post_originals_in_order:
                if file_path in globally_processed_files:
                    log_file.write(f"  [Content Image SKIPPED] Path: {file_path} (already processed)\n")
                    continue
                
                globally_processed_files.add(file_path)
                original_basename, original_ext = os.path.splitext(os.path.basename(file_path))
                suffix = "_o" if original_basename.lower().endswith('_o') else ""
                new_filename_base = f"{slug}-{post_image_counter + 1}{suffix}"
                new_path = os.path.join(images_path, slug, f"{new_filename_base}{original_ext}")

                log_file.write(f"  [Content Image {post_image_counter}]\n")
                log_file.write(f"    - Original Path: {file_path}\n")
                log_file.write(f"    - New Path     : {new_path}\n")

                image_tasks.append((file_path, slug, new_filename_base, images_path, 'images', False))
                
                relative_original = os.path.relpath(file_path, images_path)
                relative_new = os.path.relpath(new_path, images_path)
                conversion_map[os.path.join('/content/images', relative_original)] = os.path.join('/content/images', relative_new)
                post_image_counter += 1

            # --- 3. Content Media (Video/Audio) ---
            post_media_counter = 0
            media_urls = []
            for tag in soup.find_all(['video', 'audio']):
                if tag.get('src'): media_urls.append(tag.get('src'))
                for source in tag.find_all('source'):
                    if source.get('src'): media_urls.append(source.get('src'))
            
            for url in set(media_urls): # Use set to avoid duplicates
                url = url.replace('__GHOST_URL__', '')
                path = urlparse(url).path

                if path.startswith('/content/media/'):
                    relative_path = path[len('/content/media/'):]
                    file_path = os.path.join(media_path, relative_path)

                    if os.path.exists(file_path) and file_path not in globally_processed_files:
                        globally_processed_files.add(file_path)
                        new_filename_base = f"{slug}-{post_media_counter + 1}"
                        new_path = os.path.join(media_path, slug, f"{new_filename_base}{os.path.splitext(file_path)[1]}")

                        log_file.write(f"  [Content Media {post_media_counter}]\n")
                        log_file.write(f"    - Original Path: {file_path}\n")
                        log_file.write(f"    - New Path     : {new_path}\n")

                        media_tasks.append((file_path, slug, new_filename_base, media_path, 'media', False))
                        
                        relative_original = os.path.relpath(file_path, media_path)
                        relative_new = os.path.relpath(new_path, media_path)
                        conversion_map[os.path.join('/content/media', relative_original)] = os.path.join('/content/media', relative_new)
                        post_media_counter += 1
                    elif file_path in globally_processed_files:
                        log_file.write(f"  [Content Media SKIPPED] Path: {file_path} (already processed)\n")

            log_file.write("\n")

    print(f"Analysis complete. Detailed plan saved to: {analysis_log_path}")
    return analysis_log_path, image_tasks, media_tasks, conversion_map

def main():
    parser = argparse.ArgumentParser(description="Reorganize Ghost CMS media based on post slugs.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode.")
    parser.add_argument('--restore', type=str, help="Path to a log file to restore from.")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No actual changes will be made. ---\n")

    verify_db_connection_or_abort(config.db_config)
    
    if args.restore:
        restore_from_log(args.restore, config.images_path, config.media_path, config.db_config, args.dry)
        print("\nProcess finished.")
        return

    # --- Analysis Phase ---
    posts = get_posts_with_media(config.db_config)
    if not posts:
        print("No posts with media found to analyze.")
        return

    analysis_log_path, image_tasks, media_tasks, conversion_map = analyze_reorganization(
        posts, config.images_path, config.media_path, config.log_path, config.db_config['database']
    )

    print("\n--- Current Configuration & Settings ---")
    print(f"Database Host: {config.db_config.get('host', 'N/A')}")
    print(f"Database Name: {config.db_config.get('database', 'N/A')}")
    print(f"Images Path: {config.images_path}")
    print(f"Media Path: {config.media_path}")
    print("----------------------------------------")
    print(f"Found {len(image_tasks)} images and {len(media_tasks)} media files to reorganize.")
    print(f"A detailed plan has been saved to: {analysis_log_path}")

    if not image_tasks and not media_tasks:
        print("No files to reorganize.")
        print("\nProcess finished.")
        return

    user_input = input("Do you want to proceed with reorganization based on the analysis? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Process aborted by user.")
        return

    # --- Execution Phase ---
    all_tasks = image_tasks + media_tasks
    if not all_tasks:
        print("No media to reorganize.")
    else:
        print(f"Starting parallel media reorganization for {len(all_tasks)} files...")
        worker_tasks = [(t[0], t[1], t[2], t[3], t[4], args.dry) for t in all_tasks]
        
        with multiprocessing.Pool() as pool:
            results = pool.map(_reorganize_worker, worker_tasks)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        exec_log_path = os.path.join(config.log_path, f"reorganize_exec_{config.db_config['database']}_{timestamp}.log")
        
        successful_conversions = {}
        with open(exec_log_path, 'w') as log_file:
            log_file.write(f"# Reorganization Log for {config.db_config['database']} at {timestamp}\n")
            for result in results:
                if result[0] == 'success':
                    _, db_path_original, db_path_new = result
                    log_file.write(f"{db_path_original} -> {db_path_new}\n")
                    successful_conversions[db_path_original] = db_path_new
                else:
                    _, file_path, error_message = result
                    error_line = f"Failed to reorganize {file_path}: {error_message}\n"
                    print(error_line.strip())
                    log_file.write(f"# FAILED: {error_line}")
        
        print(f"Execution finished. Log saved to: {exec_log_path}")

        # Update database using only the successful conversions from the execution phase
        update_database_links(config.db_config, successful_conversions, args.dry)

    print("\nProcess finished.")

if __name__ == "__main__":
    main()
