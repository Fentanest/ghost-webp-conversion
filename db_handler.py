# db_handler.py
import re
import os
import datetime
import subprocess
import mysql.connector
import json
from bs4 import BeautifulSoup

def backup_database(db_config, backup_path, nobackup=False, dry_run=False):
    """
    Dumps the MySQL database to a .sql file.
    """
    if nobackup:
        print("Skipping database backup as per --nobackup option.")
        return None

    if dry_run:
        print(f"DRY RUN: Would backup database '{db_config['database']}' to {os.path.join(backup_path, f"db_backup_{db_config['database']}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.sql")}")
        return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"db_backup_{db_config['database']}_{timestamp}.sql"
    backup_filepath = os.path.join(backup_path, backup_filename)

    if not os.path.exists(backup_path):
        os.makedirs(backup_path)

    print(f"Backing up database '{db_config['database']}' to {backup_filepath}...")

    try:
        # Construct the mysqldump command
        command = [
            'mysqldump',
            f'--user={db_config["user"]}',
            f'--password={db_config["password"]}',
            f'--host={db_config["host"]}',
            db_config['database']
        ]

        # Execute the command and write the output to the backup file
        with open(backup_filepath, 'w') as f:
            subprocess.run(command, stdout=f, check=True, text=True)

        print("Database backup completed.")
        return backup_filepath
    except subprocess.CalledProcessError as e:
        print(f"Error during database backup: {e}")
        # Clean up the failed backup file
        if os.path.exists(backup_filepath):
            os.remove(backup_filepath)
        return None
    except FileNotFoundError:
        print("Error: 'mysqldump' command not found. Please make sure MySQL client tools are installed and in your PATH.")
        return None

def backup_plaintext(db_config, backup_path, dry_run=False):
    """
    Backs up the id, slug, and plaintext of posts containing images.
    """
    posts_to_backup = []
    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                # A simple query to find posts that might contain images.
                query = """
                SELECT id, slug, plaintext FROM posts 
                WHERE plaintext LIKE '%%.png%%' OR plaintext LIKE '%%.jpg%%' 
                OR plaintext LIKE '%%.jpeg%%' OR plaintext LIKE '%%.gif%%'
                """
                cursor.execute(query)
                posts_to_backup = cursor.fetchall()
    except mysql.connector.Error as e:
        print(f"Database error during plaintext backup query: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during plaintext backup query: {e}")
        return None

    if not posts_to_backup:
        print("No posts with image links found in plaintext. Skipping plaintext backup.")
        return None

    if dry_run:
        print(f"DRY RUN: Would backup plaintext for {len(posts_to_backup)} posts to {os.path.join(backup_path, f"plaintext_backup_{db_config['database']}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json")}")
        return None # Return None as no file is actually created

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"plaintext_backup_{db_config['database']}_{timestamp}.json"
    backup_filepath = os.path.join(backup_path, backup_filename)
    
    with open(backup_filepath, 'w', encoding='utf-8') as f:
        json.dump(posts_to_backup, f, indent=4, ensure_ascii=False)
    
    print(f"Successfully backed up plaintext for {len(posts_to_backup)} posts to {backup_filepath}")
    return backup_filepath


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
    # This regex needs to be more robust to handle cases like /content/images/size/w600/2025/10/image.png
    # and extract just the /size/wXXX/ part
    size_match = re.match(r'(/content/images/size/w\d+/)', url)
    if size_match:
        size_prefix = size_match.group(1)
        # For map lookup, we need the path without the size prefix,
        # so replace /content/images/size/wXXX/ with /content/images/
        url_for_map_lookup = url.replace(size_prefix, '/content/images/', 1)
    else:
        url_for_map_lookup = url

    # The key for conversion_map should be like /content/images/YYYY/MM/image.png
    map_key = url_for_map_lookup

    if map_key in conversion_map:
        new_map_value = conversion_map[map_key]
        # Reconstruct the URL with original prefixes
        # The new_map_value already has /content/images/
        # We need to re-insert the size_prefix if it was there
        if size_prefix:
            # Replace /content/images/ with size_prefix in the new_map_value
            new_url_path = new_map_value.replace('/content/images/', size_prefix, 1)
        else:
            new_url_path = new_map_value
        
        return f"{ghost_url_prefix}{new_url_path}"
    return original_url # Return original if not found in map


def update_image_links(db_config, conversion_map, dry_run=False, log_path=None, database_name=None):
    """
    Updates image links in the posts table (html, feature_image) and settings table 
    (logo, cover_image, icon) using the conversion_map.
    Handles src and srcset attributes in HTML.
    """
    updated_posts_count = 0
    updated_settings_count = 0
    
    html_log_file = None
    try:
        if dry_run:
            if not log_path or not database_name:
                print("Error: log_path or database_name not provided for HTML dry run logging.")
                return -1, -1
            if not os.path.exists(log_path):
                os.makedirs(log_path)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            html_dry_run_log_filepath = os.path.join(log_path, f"html_update_dry_run_{database_name}_{timestamp}.log")
            print(f"DRY RUN: Detailed HTML changes will be logged to: {html_dry_run_log_filepath}")
            html_log_file = open(html_dry_run_log_filepath, 'w', encoding='utf-8')

        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                # --- Posts Table Update ---
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
                                    if new_url != url:
                                        html_changed = True
                                    
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
                        updated_posts_count += 1
                        if dry_run:
                            html_log_file.write(f"--- DRY RUN: Post ID {post['id']} ---\n")
                            if html_changed:
                                html_log_file.write(f"Original HTML:\n{original_html}\nNew HTML:\n{new_html}\n")
                            if feature_image_changed:
                                html_log_file.write(f"Original Feature Image: {original_feature_image}\nNew Feature Image: {new_feature_image}\n")
                            html_log_file.write("---------------------------------------------------\n")
                            print(f"DRY RUN: Post ID {post['id']} would be updated.")
                        else:
                            update_query = "UPDATE posts SET html = %s, feature_image = %s WHERE id = %s"
                            cursor.execute(update_query, (new_html, new_feature_image, post['id']))

                # --- Settings Table Update ---
                setting_keys = ('logo', 'cover_image', 'icon')
                # Using a format string for the IN clause
                query_template = "SELECT id, `key`, `value` FROM settings WHERE `key` IN ({})"
                in_clause = ', '.join(['%s'] * len(setting_keys))
                query = query_template.format(in_clause)

                cursor.execute(query, setting_keys)
                settings = cursor.fetchall()

                for setting in settings:
                    original_value = setting['value']
                    if not original_value:
                        continue

                    new_value = _process_image_url(original_value, conversion_map)

                    if new_value != original_value:
                        updated_settings_count += 1
                        if dry_run:
                            html_log_file.write(f"--- DRY RUN: Setting Key '{setting['key']}' ---\n")
                            html_log_file.write(f"Original Value: {original_value}\n")
                            html_log_file.write(f"New Value: {new_value}\n")
                            html_log_file.write("---------------------------------------------------\n")
                            print(f"DRY RUN: Setting '{setting['key']}' would be updated.")
                        else:
                            update_query = "UPDATE settings SET `value` = %s WHERE id = %s"
                            cursor.execute(update_query, (new_value, setting['id']))

                if not dry_run:
                    conn.commit()
                
                print(f"Successfully processed {updated_posts_count} posts.")
                print(f"Successfully processed {updated_settings_count} settings.")
                return updated_posts_count, updated_settings_count

    except mysql.connector.Error as e:
        print(f"Database error during link update: {e}")
        return -1, -1
    except Exception as e:
        print(f"An unexpected error occurred during link update: {e}")
        return -1, -1
    finally:
        if html_log_file:
            html_log_file.close()

def restore_plaintext(db_config, plaintext_backup_path, dry_run=False):
    """
    Restores the original plaintext to the posts table.
    """
    if not plaintext_backup_path or not os.path.exists(plaintext_backup_path):
        print("Plaintext backup file not found. Skipping restoration.")
        return 0

    with open(plaintext_backup_path, 'r', encoding='utf-8') as f:
        backed_up_posts = json.load(f)

    if not backed_up_posts:
        print("No posts in the backup file. Skipping restoration.")
        return 0

    if dry_run:
        print(f"DRY RUN: Would restore plaintext for {len(backed_up_posts)} posts.")
        return 0 # Return 0 as no actual restores

    restored_count = 0
    try:
        with mysql.connector.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                for post in backed_up_posts:
                    update_query = "UPDATE posts SET plaintext = %s WHERE id = %s"
                    cursor.execute(update_query, (post['plaintext'], post['id']))
                    restored_count += 1
                
                conn.commit()
                print(f"Successfully restored plaintext for {restored_count} posts.")
                return restored_count

    except mysql.connector.Error as e:
        print(f"Database error during plaintext restoration: {e}")
        # conn.rollback() # Rollback is handled by 'with' context manager on error
        return -1
    except Exception as e:
        print(f"An unexpected error occurred during plaintext restoration: {e}")
        return -1
