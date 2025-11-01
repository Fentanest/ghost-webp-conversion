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
    """Analyzes all posts to find images that need alt tag updates."""
    print("Analyzing posts for alt tag updates...")
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token.")
        return None, None

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    posts_url = f"{api_url}/ghost/api/admin/posts/?limit=all&formats=html"

    changes_log = []
    posts_to_update = []

    try:
        print("Fetching all posts via API...")
        response = requests.get(posts_url, headers=headers)
        response.raise_for_status()
        posts = response.json().get('posts', [])
        print(f"Found {len(posts)} posts to check.")

        for post in posts:
            post_changed = False
            html = post.get('html')
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
                                'post_slug': post.get('slug'),
                                'image_src': src,
                                'old_alt': old_alt_text,
                                'new_alt': new_alt_text
                            }
                            changes_log.append(change_details)
                            tag['alt'] = new_alt_text
                            post_changed = True
                    except Exception as e:
                        print(f"Could not process src '{src}' in post '{post.get('slug')}': {e}")
            
            if post_changed:
                post['soup'] = soup # Attach modified soup object for later
                posts_to_update.append(post)

        return posts_to_update, changes_log

    except requests.exceptions.RequestException as e:
        print(f"API error while fetching posts: {e}")
        if e.response:
            print(f"Response: {e.response.text}")
        return None, None

def execute_alt_tag_updates(posts_to_update):
    """Executes the API calls to update posts with new alt tags."""
    print(f"\nExecuting updates for {len(posts_to_update)} posts...")
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token for execution.")
        return

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    updated_count = 0

    with requests.Session() as s:
        s.headers.update(headers)
        for post in posts_to_update:
            post['html'] = str(post.pop('soup')) # Get HTML from soup and remove it
            try:
                post.pop('mobiledoc', None)
                update_url = f"{api_url}/ghost/api/admin/posts/{post['id']}/?source=html"
                response = s.put(update_url, json={'posts': [post]})
                response.raise_for_status()
                print(f"Successfully updated post: {post.get('slug')}")
                updated_count += 1
            except requests.exceptions.RequestException as e:
                print(f"Error updating post {post.get('slug')}: {e.response.text}")
    
    print(f"\nSuccessfully updated {updated_count} posts.")

def restore_alt_tags(log_filepath, dry_run=False):
    """Restores alt tags from a given log file."""
    print(f"--- Starting alt tag restoration from log: {log_filepath} ---")

    if not os.path.exists(log_filepath):
        print(f"Error: Log file not found at {log_filepath}")
        return

    with open(log_filepath, 'r', encoding='utf-8') as f:
        changes_log = json.load(f)

    if not changes_log:
        print("Log file is empty. Nothing to restore.")
        return

    # Group changes by post slug
    changes_by_slug = {}
    for change in changes_log:
        slug = change['post_slug']
        if slug not in changes_by_slug:
            changes_by_slug[slug] = []
        changes_by_slug[slug].append(change)

    print(f"Found {len(changes_log)} changes to restore across {len(changes_by_slug)} posts.")

    # Fetch all posts to get their current state
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token.")
        return
    
    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    posts_url = f"{api_url}/ghost/api/admin/posts/?limit=all&formats=html"
    
    try:
        response = requests.get(posts_url, headers=headers)
        response.raise_for_status()
        all_posts = response.json().get('posts', [])
        posts_map = {post['slug']: post for post in all_posts}
    except requests.exceptions.RequestException as e:
        print(f"API error while fetching posts: {e}")
        return

    posts_to_update = []
    for slug, changes in changes_by_slug.items():
        if slug not in posts_map:
            print(f"Warning: Post with slug '{slug}' not found. Skipping.")
            continue

        post = posts_map[slug]
        html = post.get('html')
        if not html:
            continue

        soup = BeautifulSoup(html, 'html.parser')
        post_changed = False

        for change in changes:
            # Find the specific image tag by src
            img_tag = soup.find('img', {'src': change['image_src']})
            if img_tag:
                img_tag['alt'] = change['old_alt']
                post_changed = True
            else:
                print(f"Warning: Image with src '{change['image_src']}' not found in post '{slug}'.")

        if post_changed:
            post['soup'] = soup
            posts_to_update.append(post)

    if not posts_to_update:
        print("No posts needed to be updated.")
        return

    print(f"\n{len(posts_to_update)} posts will be restored.")
    if dry_run:
        print("--- DRY RUN: The following posts would be restored ---")
        for post in posts_to_update:
            print(f"- {post.get('slug')}")
        return

    user_input = input("Are you sure you want to restore these alt tags? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Restoration aborted by user.")
        return

    execute_alt_tag_updates(posts_to_update)
    print("\n--- Alt tag restoration process finished successfully! ---")

def main():
    parser = argparse.ArgumentParser(description="Automatically add or restore alt tags to images in Ghost posts.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No changes will be made.")
    parser.add_argument('--force', action='store_true', help="Force overwrite of existing alt tags.")
    parser.add_argument('--restore', type=str, metavar='LOG_FILE', help="Restore alt tags from a given alt_tags_log JSON file.")
    args = parser.parse_args()

    if args.restore:
        restore_alt_tags(args.restore, args.dry)
        return

    # 1. Analyze and generate the change list
    posts_to_update, changes_log = analyze_alt_tags(force=args.force)

    if posts_to_update is None:
        print("\nProcess failed during analysis.")
        return

    # 2. Save the JSON log file
    if changes_log:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    updated_posts_count = len(posts_to_update)
    print(f"\nAnalysis complete. Found {len(changes_log)} images to change across {updated_posts_count} posts.")
    print(f"Check the detailed plan at: {log_filepath}")

    if args.dry:
        print("\n--- DRY RUN complete. No changes will be made. ---")
        return

    user_input = input("Do you want to proceed with these updates? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Process aborted by user.")
        return

    # 4. Execute the updates
    execute_alt_tag_updates(posts_to_update)

    print("\nAlt tag update process finished successfully!")

if __name__ == "__main__":
    main()
