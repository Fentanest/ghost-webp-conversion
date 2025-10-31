# api_handler.py
import config
import requests
import jwt
import logging
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from file_handler import _process_url

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
            headers={
                'alg': 'HS256',
                'typ': 'JWT',
                'kid': key_id
            }
        )
        return token
    except Exception as e:
        logging.error(f"Error generating JWT: {e}")
        return None

def update_image_links_via_api(conversion_map, dry_run=False, log_path='.', database_name='ghost'):
    """
    Updates image links in posts and settings using direct requests to the Ghost Admin API.
    Returns the number of updated posts and settings.
    """
    if not conversion_map:
        print("Conversion map is empty, nothing to update.")
        return 0, 0

    token = generate_jwt(config.ghost_admin_api_key)
    if not token:
        print("Failed to generate API token. Please check your Admin API Key in config.py.")
        return -1, -1

    headers = {'Authorization': f'Ghost {token}'}
    api_url = config.ghost_api_url.rstrip('/')

    # Setup standard logging
    log_file = f"{log_path}/api_update_log_{database_name}.log"
    logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Setup detailed debug logging
    api_debug_log_path = os.path.join(log_path, f"api_detailed_debug_{database_name}.log")
    with open(api_debug_log_path, 'w') as f:
        f.write(f"--- API Update Detailed Debug Log ---\nRun at: {datetime.now()}\n\n")
        f.write("--- Conversion Map Sample (first 100 entries) ---\n")
        for i, (key, value) in enumerate(conversion_map.items()):
            if i >= 100: break
            f.write(f"KEY  : {key}\nVALUE: {value}\n---\n")

    updated_posts_count = 0
    updated_settings_count = 0

    with requests.Session() as s:
        s.headers.update(headers)

        # --- Update Posts ---
        try:
            posts_url = f"{api_url}/ghost/api/admin/posts/?limit=all&formats=html,mobiledoc"
            print("Fetching all posts via Ghost API...")
            response = s.get(posts_url)
            response.raise_for_status()
            posts = response.json().get('posts', [])
            print(f"Found {len(posts)} posts to check.")

            for post in posts:
                original_html = post.get('html', '')
                if not original_html:
                    continue

                with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n============================================================\n")
                    f.write(f"Processing Post ID: {post['id']}, Slug: {post['slug']}\n")
                    f.write(f"============================================================\n\n")
                    f.write("--- Original HTML ---\n")
                    f.write(original_html + "\n\n")

                soup = BeautifulSoup(original_html, 'html.parser')
                html_changed = False

                # Update <img>, <video>, <audio> tags
                for tag in soup.find_all(['img', 'video', 'audio']):
                    # Process 'src'
                    if tag.has_attr('src'):
                        old_src = tag['src']
                        new_src = _process_url(old_src, conversion_map)
                        with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                            f.write(f"--- Checking src ---\n")
                            f.write(f"Found URL: {old_src}\n")
                            f.write(f"Converted: {new_src}\n")
                            f.write(f"Changed  : {new_src != old_src}\n\n")
                        if new_src != old_src:
                            tag['src'] = new_src
                            html_changed = True
                            
                    # Process 'srcset' for <img>
                    if tag.name == 'img' and tag.has_attr('srcset'):
                        old_srcset = tag['srcset']
                        new_srcset_parts = []
                        for part in old_srcset.split(','):
                            part = part.strip()
                            if not part: continue
                            url_descriptor = part.rsplit(' ', 1)
                            url, descriptor = (url_descriptor[0], url_descriptor[1]) if len(url_descriptor) > 1 else (url_descriptor[0], '')
                            new_url = _process_url(url, conversion_map)
                            with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                                f.write(f"--- Checking srcset part ---\n")
                                f.write(f"Found URL: {url}\n")
                                f.write(f"Converted: {new_url}\n")
                                f.write(f"Changed  : {new_url != url}\n\n")
                            new_srcset_parts.append(f"{new_url} {descriptor}" if descriptor else new_url)
                        new_srcset = ", ".join(new_srcset_parts)
                        if new_srcset != old_srcset:
                            tag['srcset'] = new_srcset
                            html_changed = True
                            
                    # Process <source> children
                    for source_tag in tag.find_all('source'):
                        if source_tag.has_attr('src'):
                            old_src = source_tag['src']
                            new_src = _process_url(old_src, conversion_map)
                            with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                                f.write(f"--- Checking <source> src ---\n")
                                f.write(f"Found URL: {old_src}\n")
                                f.write(f"Converted: {new_src}\n")
                                f.write(f"Changed  : {new_src != old_src}\n\n")
                            if new_src != old_src:
                                source_tag['src'] = new_src
                                html_changed = True
                
                # --- Process Feature Image ---
                old_feature_image = post.get('feature_image')
                if old_feature_image:
                    new_feature_image = _process_url(old_feature_image, conversion_map)
                    
                    with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                        f.write(f"--- Checking feature_image ---\n")
                        f.write(f"Found URL: {old_feature_image}\n")
                        f.write(f"Converted: {new_feature_image}\n")
                        f.write(f"Changed  : {new_feature_image != old_feature_image}\n\n")

                    if new_feature_image != old_feature_image:
                        post['feature_image'] = new_feature_image
                        html_changed = True # Use the same flag to trigger an update

                if html_changed:
                    modified_html = str(soup)
                    post['html'] = modified_html
                    with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                        f.write("--- Final (Modified) HTML ---\n")
                        f.write(modified_html + "\n\n")
                    
                    if not dry_run:
                        try:
                            post.pop('mobiledoc', None)
                            update_url = f"{api_url}/ghost/api/admin/posts/{post['id']}/?source=html"
                            response = s.put(update_url, json={'posts': [post]})
                            response.raise_for_status()
                            logging.info(f"Successfully updated post ID {post['id']} ('{post['slug']}').")
                            updated_posts_count += 1
                        except requests.exceptions.RequestException as e:
                            error_msg = f"Error updating post ID {post['id']} via API: {e.response.text}"
                            print(error_msg)
                            logging.error(error_msg)
                else:
                    with open(api_debug_log_path, 'a', encoding='utf-8') as f:
                        f.write("--- No changes made to HTML ---\n\n")

        except requests.exceptions.RequestException as e:
            error_msg = f"Error fetching posts via API: {e.response.text if e.response else e}"
            print(error_msg)
            logging.error(error_msg)
            return -1, -1

    print(f"\nAPI update process finished.")
    print(f"Updated {updated_posts_count} posts and 0 settings.")
    logging.info(f"Finished. Updated {updated_posts_count} posts and 0 settings.")
    
    return updated_posts_count, 0