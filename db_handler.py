# db_handler.py
import os
import datetime
import subprocess
import mysql.connector
import json

def backup_database(db_config, backup_path):
    """
    Dumps the MySQL database to a .sql file.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"db_backup_{timestamp}.sql"
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

def backup_plaintext(db_config, backup_path):
    """
    Backs up the id, slug, and plaintext of posts containing images.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"plaintext_backup_{timestamp}.json"
    backup_filepath = os.path.join(backup_path, backup_filename)
    
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

        if not posts_to_backup:
            print("No posts with image links found in plaintext. Skipping plaintext backup.")
            return None

        with open(backup_filepath, 'w', encoding='utf-8') as f:
            json.dump(posts_to_backup, f, indent=4, ensure_ascii=False)
        
        print(f"Successfully backed up plaintext for {len(posts_to_backup)} posts to {backup_filepath}")
        return backup_filepath

    except mysql.connector.Error as e:
        print(f"Database error during plaintext backup: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during plaintext backup: {e}")
        return None

def update_image_links(db_config, conversion_map):
    """
    Updates image links in the posts table (html and feature_image).
    """
    updated_posts_count = 0
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

                    for original_path, webp_path in conversion_map.items():
                        # Note: Ghost paths might be relative or absolute. 
                        # This simple replacement should work for default Ghost setups.
                        if original_html:
                            new_html = new_html.replace(original_path, webp_path)
                        if new_feature_image:
                            new_feature_image = new_feature_image.replace(original_path, webp_path)

                    if new_html != original_html or new_feature_image != original_feature_image:
                        update_query = "UPDATE posts SET html = %s, feature_image = %s WHERE id = %s"
                        cursor.execute(update_query, (new_html, new_feature_image, post['id']))
                        updated_posts_count += 1
                
                conn.commit()
                print(f"Successfully updated image links in {updated_posts_count} posts.")
                return updated_posts_count

    except mysql.connector.Error as e:
        print(f"Database error during link update: {e}")
        # conn.rollback() # Rollback is handled by 'with' context manager on error
        return -1
    except Exception as e:
        print(f"An unexpected error occurred during link update: {e}")
        return -1

def restore_plaintext(db_config, plaintext_backup_path):
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