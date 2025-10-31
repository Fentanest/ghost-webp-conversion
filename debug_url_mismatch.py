# debug_url_mismatch.py
import os
import config
from file_handler import find_images, convert_images_to_webp
import requests
import jwt
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def generate_jwt(api_key):
    """Generates a JWT for Ghost Admin API authentication."""
    try:
        key_id, secret = api_key.split(':')
        secret_bytes = bytes.fromhex(secret)
        payload = {
            'iat': int(datetime.now().timestamp()),
            'exp': int((datetime.now() + timedelta(minutes=5)).timestamp()),
            'aud': '/admin/'
        }
        token = jwt.encode(
            payload,
            secret_bytes,
            algorithm='HS256',
            headers={'alg': 'HS256', 'typ': 'JWT', 'kid': key_id}
        )
        return token
    except Exception as e:
        print(f"Error generating JWT: {e}")
        return None

def main():
    """Runs a focused debugging process to diagnose URL mismatches."""
    # 1. Generate the conversion_map (in dry_run mode)
    print("--- Step 1: Finding images and generating conversion map (Dry Run) ---")
    database_name = config.db_config.get('database', 'ghost')
    
    # Use a temporary path for logs to avoid clutter
    temp_log_path = '.' 

    all_images, duplicates = find_images(config.images_path, temp_log_path, database_name)
    if not all_images:
        print("No images found in the specified images_path.")
        return

    conversion_map = convert_images_to_webp(
        all_images, 
        duplicates, 
        config.webp_quality, 
        temp_log_path, 
        config.images_path, 
        database_name, 
        config.ghost_api_url, # Added this argument
        dry_run=True # Use dry_run to avoid re-conversion and speed up the process
    )
    if not conversion_map:
        print("Failed to generate conversion map.")
        return
    print(f"Generated a conversion map with {len(conversion_map)} entries.")

    # 2. Fetch the first post from Ghost API
    print("\n--- Step 2: Fetching first post from Ghost API ---")
    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token. Check your config.py.")
        return
        
    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')
    
    try:
        # Fetch only the first post
        posts_url = f"{api_url}/ghost/api/admin/posts/?limit=1&formats=html"
        response = requests.get(posts_url, headers=headers)
        response.raise_for_status()
        posts = response.json().get('posts', [])
        if not posts:
            print("Could not fetch any posts from the API.")
            return
        first_post = posts[0]
        print(f"Successfully fetched post: '{first_post.get('title')}'")
    except Exception as e:
        print(f"Error fetching post from API: {e}")
        return

    # 3. Write the debug log
    print("\n--- Step 3: Writing debug log ---")
    debug_log_path = "url_debug_log.log" # Write to current directory
    with open(debug_log_path, 'w') as debug_log:
        debug_log.write("--- Conversion Map Sample ---\n")
        for i, (key, value) in enumerate(conversion_map.items()):
            if i >= 50: break
            debug_log.write(f"{key} -> {value}\n")
        
        debug_log.write("\n--- URLs found in first post ---\n")
        soup = BeautifulSoup(first_post.get('html', ''), 'html.parser')
        urls_found = []
        for tag in soup.find_all(['img', 'video', 'audio']):
            if tag.has_attr('src'): urls_found.append(tag['src'])
            if tag.name == 'img' and tag.has_attr('srcset'):
                for part in tag['srcset'].split(','):
                    urls_found.append(part.strip().split(' ')[0])
            for source_tag in tag.find_all('source'):
                if source_tag.has_attr('src'): urls_found.append(source_tag['src'])
        for url in set(urls_found):
            debug_log.write(f"{url}\n")
            
    print(f"\nDebug log created at: {os.path.abspath(debug_log_path)}")

if __name__ == "__main__":
    main()
