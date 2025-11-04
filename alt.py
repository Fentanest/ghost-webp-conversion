# alt.py
import os
import config
import argparse
import requests
import json
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Import shared API functions
from api_handler import generate_jwt

def analyze_alt_tags(force=False):
    """Analyzes all posts and pages to find images that need alt tag updates."""
    print("Analyzing posts and pages for alt tag updates...")
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token.")
        return None, None

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    
    changes_log = []
    items_to_update = []

    for content_type in ['posts', 'pages']:
        try:
            content_url = f"{api_url}/ghost/api/admin/{content_type}/?limit=all&formats=html&filter=status:[published,scheduled]"
            print(f"Fetching all published and scheduled {content_type} via API...")
            response = requests.get(content_url, headers=headers)
            response.raise_for_status()
            items = response.json().get(content_type, [])
            print(f"Found {len(items)} {content_type} to check.")

            for item in items:
                item_changed = False
                html = item.get('html')
                if not html:
                    continue

                soup = BeautifulSoup(html, 'html.parser')
                img_tags = soup.find_all('img')

                for tag in img_tags:
                    # Skip images within a thumbnail or metadata bookmark
                    if tag.find_parent("div", class_=("kg-bookmark-thumbnail", "kg-bookmark-metadata")):
                        continue

                    old_alt_text = tag.get('alt', '')
                    if force or not old_alt_text.strip():
                        src = tag.get('src')
                        if not src:
                            continue
                        
                        try:
                            filename = os.path.basename(urlparse(src).path)
                            _, ext = os.path.splitext(filename)
                            if not ext or ext.lower() == '.ico':
                                continue

                            new_alt_text = f"image-{filename}"
                            if old_alt_text != new_alt_text:
                                change_details = {
                                    'post_slug': item.get('slug'),
                                    'image_src': src,
                                    'old_alt': old_alt_text,
                                    'new_alt': new_alt_text,
                                    'content_type': content_type
                                }
                                changes_log.append(change_details)
                                tag['alt'] = new_alt_text
                                item_changed = True
                        except Exception as e:
                            print(f"Could not process src '{src}' in {content_type[:-1]} '{item.get('slug')}': {e}")
                
                if item_changed:
                    item['soup'] = soup # Attach modified soup object for later
                    item['content_type'] = content_type # Add content type for the execution function
                    items_to_update.append(item)

        except requests.exceptions.RequestException as e:
            print(f"API error while fetching {content_type}: {e}")
            if e.response:
                print(f"Response: {e.response.text}")
            return None, None

    return items_to_update, changes_log

def execute_alt_tag_updates(items_to_update):
    """Executes the API calls to update posts and pages with new alt tags."""
    print(f"\nExecuting updates for {len(items_to_update)} items...")
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token for execution.")
        return

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    updated_count = 0

    with requests.Session() as s:
        s.headers.update(headers)
        for item in items_to_update:
            content_type = item.pop('content_type', 'posts') # Default to posts for backward compatibility
            item['html'] = str(item.pop('soup')) # Get HTML from soup and remove it
            try:
                item.pop('mobiledoc', None)
                update_url = f"{api_url}/ghost/api/admin/{content_type}/{item['id']}/?source=html"
                response = s.put(update_url, json={content_type: [item]})
                response.raise_for_status()
                print(f"Successfully updated {content_type[:-1]}: {item.get('slug')}")
                updated_count += 1
            except requests.exceptions.RequestException as e:
                print(f"Error updating {content_type[:-1]} {item.get('slug')}: {e.response.text}")
    
    print(f"\nSuccessfully updated {updated_count} items.")

def restore_alt_tags(log_filepath, dry_run=False, assume_yes=False):
    """Restores alt tags from a given log file for both posts and pages."""
    print(f"--- Starting alt tag restoration from log: {log_filepath} ---")

    if not os.path.exists(log_filepath):
        print(f"Error: Log file not found at {log_filepath}")
        return

    with open(log_filepath, 'r', encoding='utf-8') as f:
        changes_log = json.load(f)

    if not changes_log:
        print("Log file is empty. Nothing to restore.")
        return

    # Group changes by content type and then by slug
    changes_by_content_type = {'posts': {}, 'pages': {}}
    for change in changes_log:
        content_type = change.get('content_type', 'posts') # Default to posts for old logs
        slug = change['post_slug']
        if slug not in changes_by_content_type[content_type]:
            changes_by_content_type[content_type][slug] = []
        changes_by_content_type[content_type][slug].append(change)

    print(f"Found {len(changes_log)} changes to restore across posts and pages.")

    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token.")
        return
    
    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    
    items_to_update = []

    for content_type, slugs in changes_by_content_type.items():
        if not slugs:
            continue

        content_url = f"{api_url}/ghost/api/admin/{content_type}/?limit=all&formats=html"
        try:
            response = requests.get(content_url, headers=headers)
            response.raise_for_status()
            all_items = response.json().get(content_type, [])
            items_map = {item['slug']: item for item in all_items}
        except requests.exceptions.RequestException as e:
            print(f"API error while fetching {content_type}: {e}")
            continue

        for slug, changes in slugs.items():
            if slug not in items_map:
                print(f"Warning: {content_type[:-1].capitalize()} with slug '{slug}' not found. Skipping.")
                continue

            item = items_map[slug]
            html = item.get('html')
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')
            item_changed = False

            for change in changes:
                img_tag = soup.find('img', {'src': change['image_src']})
                if img_tag:
                    img_tag['alt'] = change['old_alt']
                    item_changed = True
                else:
                    print(f"Warning: Image with src '{change['image_src']}' not found in {content_type[:-1]} '{slug}'.")

            if item_changed:
                item['soup'] = soup
                item['content_type'] = content_type
                items_to_update.append(item)

    if not items_to_update:
        print("No items needed to be updated.")
        return

    print(f"\n{len(items_to_update)} posts/pages will be restored.")
    if dry_run:
        print("--- DRY RUN: The following items would be restored ---")
        for item in items_to_update:
            print(f"- {item.get('content_type', 'posts')[:-1].capitalize()}: {item.get('slug')}")
        return

    if not assume_yes:
        user_input = input("Are you sure you want to restore these alt tags? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Restoration aborted by user.")
            return
    else:
        print("Bypassing prompt due to --yes flag.")

    execute_alt_tag_updates(items_to_update)
    print("\n--- Alt tag restoration process finished successfully! ---")

def main(timestamp):
    parser = argparse.ArgumentParser(description="Automatically add or restore alt tags to images in Ghost posts and pages.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No changes will be made.")
    parser.add_argument('--force', action='store_true', help="Force overwrite of existing alt tags.")
    parser.add_argument('--restore', type=str, metavar='LOG_FILE', help="Restore alt tags from a given alt_tags_log JSON file.")
    parser.add_argument('--yes', action='store_true', help="Bypass all interactive prompts.")
    args = parser.parse_args()

    if args.restore:
        restore_alt_tags(args.restore, args.dry, args.yes)
        return

    # 1. Analyze and generate the change list
    items_to_update, changes_log = analyze_alt_tags(force=args.force)

    if items_to_update is None:
        print("\nProcess failed during analysis.")
        return

    # 2. Save the JSON log file
    if changes_log:
        log_path = config.log_path
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        log_filepath = os.path.join(log_path, f"alt_tags_log_{timestamp}.json")
        
        print(f"\nSaving alt tag change log to: {log_filepath}")
        with open(log_filepath, 'w', encoding='utf-8') as f:
            json.dump(changes_log, f, indent=2, ensure_ascii=False)
    else:
        print("\nNo alt tags needed to be changed. Process finished.")
        return

    # 3. Handle dry run or ask for confirmation
    updated_items_count = len(items_to_update)
    print(f"\nAnalysis complete. Found {len(changes_log)} images to change across {updated_items_count} posts/pages.")
    print(f"Check the detailed plan at: {log_filepath}")

    if args.dry:
        print("\n--- DRY RUN complete. No changes will be made. ---")
        return

    if not args.yes:
        user_input = input("Do you want to proceed with these updates? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Process aborted by user.")
            return
    else:
        print("Bypassing prompt due to --yes flag.")

    # 4. Execute the updates
    execute_alt_tag_updates(items_to_update)

    print("\nAlt tag update process finished successfully!")

if __name__ == "__main__":
    execution_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    main(timestamp=execution_timestamp)
