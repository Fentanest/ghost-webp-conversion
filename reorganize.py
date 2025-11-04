# reorganize.py
import os
import re
import config
import argparse
from datetime import datetime, timedelta
import json
import mimetypes
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Import shared API functions
from api_handler import generate_jwt, update_image_links_via_api

def get_all_content_via_api():
    """Fetches all posts and pages from the Ghost API with the necessary fields for reorganization."""
    print("Fetching all posts and pages via API...")
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token.")
        return None

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    all_items = []

    for content_type in ['posts', 'pages']:
        content_url = f"{api_url}/ghost/api/admin/{content_type}/?limit=all&formats=html,mobiledoc&fields=slug,id,html,feature_image,mobiledoc&filter=status:[published,scheduled]"
        try:
            response = requests.get(content_url, headers=headers)
            response.raise_for_status()
            items = response.json().get(content_type, [])
            all_items.extend(items)
            print(f"Found {len(items)} {content_type} to analyze.")
        except requests.exceptions.RequestException as e:
            print(f"API error while fetching {content_type}: {e}")
            return None
            
    return all_items

def analyze_and_generate_map(content_items, images_path, media_path, ghost_api_url):
    """Analyzes posts and pages, determines new paths for media, and generates a map and a list of file move operations."""
    print("Analyzing media paths for reorganization...")
    reorganization_map = {}
    file_move_operations = []
    globally_processed_files = set()
    api_url_base = ghost_api_url.rstrip('/')

    # Sort items by slug to have some consistency
    content_items.sort(key=lambda p: p.get('slug', ''))

    for item in content_items:
        slug = item.get('slug')
        if not slug:
            print(f"Skipping item ID {item.get('id')} because it has no slug.")
            continue

        soup = BeautifulSoup(item.get('html') or '', 'html.parser')
        media_counter = 0

        # --- 1. Gather all media URLs from the item (feature_image, src, srcset) ---
        urls_to_process = []
        if item.get('feature_image'):
            urls_to_process.append(item['feature_image'])

        for tag in soup.find_all(['img', 'video', 'audio', 'source']):
            # Skip media within a thumbnail or metadata bookmark
            if tag.find_parent("div", class_=("kg-bookmark-thumbnail", "kg-bookmark-metadata")):
                continue
            if tag.get('src'):
                urls_to_process.append(tag['src'])
            if tag.get('srcset'):
                urls_to_process.extend([s.strip().split(' ')[0] for s in tag['srcset'].split(',') if s.strip()])

        # --- 2. Process unique URLs for this post ---
        # Use a list to preserve order for naming (slug-1, slug-2, etc.)
        unique_post_urls = []
        for url in urls_to_process:
            if url not in unique_post_urls:
                unique_post_urls.append(url)

        for url in unique_post_urls:
            try:
                parsed_url = urlparse(url)
                path = parsed_url.path
                filename = os.path.basename(path)

                # Exclude files without extension or .ico files
                _, ext = os.path.splitext(filename)
                if not ext or ext.lower() == '.ico':
                    continue

            except ValueError:
                continue # Skip malformed URLs

            if not path.startswith(('/content/images/', '/content/media/')):
                continue

            # Determine if it's an image or media file and set the base path
            if path.startswith('/content/images/'):
                base_path = images_path
                content_dir = 'images'
                relative_path = path[len('/content/images/'):]
            else: # /content/media/
                base_path = media_path
                content_dir = 'media'
                relative_path = path[len('/content/media/'):]

            normalized_relative_path = re.sub(r'size/w\d+/', '', relative_path).replace('//', '/')
            
            # Check if the file is already in a slug-based directory
            if normalized_relative_path.startswith(slug + '/'):
                continue

            original_abs_path = os.path.join(base_path, normalized_relative_path)

            if not os.path.exists(original_abs_path) or original_abs_path in globally_processed_files:
                continue # Skip if file doesn't exist or was already handled

            globally_processed_files.add(original_abs_path)
            media_counter += 1
            
            original_basename, original_ext = os.path.splitext(os.path.basename(original_abs_path))

            if not original_ext:
                mimetype, _ = mimetypes.guess_type(original_abs_path)
                if mimetype:
                    guessed_ext = mimetypes.guess_extension(mimetype)
                    if guessed_ext:
                        original_ext = guessed_ext

            new_filename = f"{slug}-{media_counter}{original_ext}"
            new_dir = os.path.join(base_path, slug)
            new_abs_path = os.path.join(new_dir, new_filename)

            # Add file move operation to the list
            file_move_operations.append((original_abs_path, new_abs_path))

            # --- Populate the map with all key/value formats ---
            old_rel_url_path = f"/content/{content_dir}/{normalized_relative_path}"
            new_rel_url_path = f"/content/{content_dir}/{slug}/{new_filename}"

            # 1. Filesystem Path -> New Filesystem Path
            reorganization_map[original_abs_path] = new_abs_path
            # 2. Relative URL Path -> New Relative URL Path
            reorganization_map[old_rel_url_path] = new_rel_url_path
            # 3. Absolute URL -> New Absolute URL
            reorganization_map[f"{api_url_base}{old_rel_url_path}"] = f"{api_url_base}{new_rel_url_path}"

    return reorganization_map, file_move_operations

def execute_file_moves(file_move_ops, dry_run=False):
    """Physically moves the files on disk based on the generated plan."""
    if not file_move_ops:
        print("No file move operations to execute.")
        return

    print(f"\nExecuting {len(file_move_ops)} file move operations...")
    moved_count = 0
    for old_path, new_path in file_move_ops:
        if os.path.abspath(old_path) == os.path.abspath(new_path):
            continue

        if dry_run:
            print(f"DRY RUN: Would move {old_path} -> {new_path}")
            moved_count += 1
            continue
        
        try:
            new_dir = os.path.dirname(new_path)
            os.makedirs(new_dir, exist_ok=True)
            os.rename(old_path, new_path)
            print(f"Moved {os.path.basename(old_path)} -> {os.path.relpath(new_path, config.images_path)}")
            moved_count += 1
        except OSError as e:
            print(f"Error moving file {old_path} to {new_path}: {e}")

    print(f"Finished moving {moved_count} files.")

def restore_from_map(map_filepath, dry_run=False, assume_yes=False):
    """Restores file locations and database entries from a reorganization map."""
    print(f"--- Starting restoration from map: {map_filepath} ---")
    
    if not os.path.exists(map_filepath):
        print(f"Error: Map file not found at {map_filepath}")
        return

    with open(map_filepath, 'r', encoding='utf-8') as f:
        reorg_map = json.load(f)

    if not reorg_map:
        print("Map file is empty. Nothing to restore.")
        return

    # 1. Create reversed map for API updates and file moves
    reversed_api_map = {}
    file_move_ops = []
    
    for old, new in reorg_map.items():
        # Reverse API URL paths
        if old.startswith('http') or old.startswith('/content/'):
            reversed_api_map[new] = old
        # Reverse file system paths
        else:
            file_move_ops.append((new, old))

    # 2. Ask for user confirmation
    print(f"Found {len(file_move_ops)} files to move back and {len(reversed_api_map)} URL references to update.")
    if dry_run:
        print("--- Running in DRY RUN mode. No actual changes will be made. ---")
    
    if not assume_yes:
        user_input = input("Are you sure you want to restore this state? This is irreversible. (yes/no): ")
        if user_input.lower() != 'yes':
            print("Restoration aborted by user.")
            return
    else:
        print("Bypassing prompt due to --yes flag.")

    # 3. Execute the file moves to restore original locations
    execute_file_moves(file_move_ops, dry_run)

    # 4. Update links via API using the reversed map
    print("\nStarting API update process to restore original URLs...")
    update_image_links_via_api(reversed_api_map, dry_run, config.log_path, "restore_reorganization")

    print("\n--- Restoration process finished successfully! ---")

def main(timestamp):
    parser = argparse.ArgumentParser(description="Reorganize Ghost CMS media into slug-based folders and update via API.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No files will be moved or API updates made.")
    parser.add_argument('--restore', type=str, metavar='MAP_FILE', help="Restore from a given reorganization_map JSON file.")
    parser.add_argument('--yes', action='store_true', help="Bypass all interactive prompts.")
    args = parser.parse_args()

    if args.restore:
        restore_from_map(args.restore, args.dry, args.yes)
        return

    if args.dry:
        print("--- Running in DRY RUN mode. No actual changes will be made. ---\n")

    # 1. Get all posts and pages via API
    content_items = get_all_content_via_api()
    if not content_items:
        return

    # 2. Analyze and generate the reorganization map and file move operations
    reorg_map, move_ops = analyze_and_generate_map(
        content_items, config.images_path, config.media_path, config.ghost_api_url
    )

    # 3. Save the generated map to a JSON file for inspection
    map_log_path = os.path.join(config.log_path, f"reorganization_map_{timestamp}.json")
    print(f"\nSaving reorganization map with {len(reorg_map)} entries to: {map_log_path}")
    with open(map_log_path, 'w', encoding='utf-8') as f:
        json.dump(reorg_map, f, indent=2, ensure_ascii=False)

    if not move_ops:
        print("\nNo files to reorganize. Process finished.")
        return

    # 4. Ask for user confirmation before proceeding
    print(f"\nAnalysis complete. {len(move_ops)} files will be moved and their links updated.")
    print(f"Check the plan at: {map_log_path}")
    if not args.yes:
        user_input = input("Do you want to proceed with this reorganization? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Process aborted by user.")
            return
    else:
        print("Bypassing prompt due to --yes flag.")

    # 5. Execute the file moves
    execute_file_moves(move_ops, args.dry)

    # 6. Update links via API using the generated map
    print("\nStarting API update process...")
    update_image_links_via_api(reorg_map, args.dry, config.log_path, "reorganize_ghost")

    print("\nReorganization process finished successfully!")

if __name__ == "__main__":
    execution_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    main(timestamp=execution_timestamp)

