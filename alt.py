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

def add_alt_tags(dry_run=False, force=False):
    """Finds images with empty or existing alt tags and updates them."""
    print("Starting alt tag update process...")

    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token.")
        return

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    
    changes_log = []

    try:
        with requests.Session() as s:
            s.headers.update(headers)

            posts_url = f"{api_url}/ghost/api/admin/posts/?limit=all&formats=html,mobiledoc"
            print("Fetching all posts via API...")
            response = s.get(posts_url)
            response.raise_for_status()
            posts = response.json().get('posts', [])
            print(f"Found {len(posts)} posts to check.")

            updated_posts = []

            for post in posts:
                post_changed = False
                html = post.get('html')
                if not html:
                    continue

                soup = BeautifulSoup(html, 'html.parser')
                img_tags = soup.find_all('img')

                for tag in img_tags:
                    old_alt_text = tag.get('alt', '')
                    if force or not old_alt_text.strip():
                        src = tag.get('src')
                        if not src:
                            continue
                        
                        try:
                            filename = os.path.basename(urlparse(src).path)
                            new_alt_text = f"image-{filename}"

                            if old_alt_text != new_alt_text:
                                change_details = {
                                    'post_slug': post.get('slug'),
                                    'image_src': src,
                                    'old_alt': old_alt_text,
                                    'new_alt': new_alt_text
                                }
                                changes_log.append(change_details)

                                if dry_run:
                                    print(f"DRY RUN: Post '{post.get('slug')}': Would change alt for '{filename}' from '{old_alt_text}' to '{new_alt_text}'")
                                
                                tag['alt'] = new_alt_text
                                post_changed = True
                        except Exception as e:
                            print(f"Could not process src '{src}' in post '{post.get('slug')}': {e}")

                if post_changed:
                    post['html'] = str(soup)
                    updated_posts.append(post)

            # 3. If changes were made, update the posts via API
            if updated_posts:
                print(f"\nFound {len(changes_log)} images to change across {len(updated_posts)} posts.")
                for post in updated_posts:
                    if not dry_run:
                        print(f"Updating post: {post.get('slug')}")
                        try:
                            post.pop('mobiledoc', None)
                            update_url = f"{api_url}/ghost/api/admin/posts/{post['id']}/?source=html"
                            response = s.put(update_url, json={'posts': [post]})
                            response.raise_for_status()
                            print(f"Successfully updated post: {post.get('slug')}")
                        except requests.exceptions.RequestException as e:
                            print(f"Error updating post {post.get('slug')}: {e.response.text}")
            else:
                print("\nNo posts required updates.")

        # Save the log of changes to a file
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
            print("\nNo alt tags needed to be changed.")

        print(f"\nAlt tag update process finished.")
        updated_posts_count = len(updated_posts)
        print(f"Processed {len(changes_log)} images across {updated_posts_count} posts.")

    except requests.exceptions.RequestException as e:
        print(f"API error while fetching posts: {e}")
        if e.response:
            print(f"Response: {e.response.text}")

def main():
    parser = argparse.ArgumentParser(description="Automatically add alt tags to images in Ghost posts.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No changes will be saved.")
    parser.add_argument('--force', action='store_true', help="Force overwrite of existing alt tags.")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No changes will be saved. ---")

    add_alt_tags(dry_run=args.dry, force=args.force)

if __name__ == "__main__":
    main()
