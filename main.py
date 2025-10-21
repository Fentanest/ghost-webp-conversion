# main.py
import config
from db_handler import backup_database, backup_plaintext, update_image_links, restore_plaintext
from file_handler import backup_ghost_files, find_images, convert_images_to_webp

def main():
    """Main function to run the conversion process."""
    print("Starting the Ghost WebP conversion process...")

    database_name = config.db_config['database']

    # Step 1: Backup
    print("\n--- Step 1: Backing up database and files ---")
    db_backup_file = backup_database(config.db_config, config.backup_path)
    ghost_backup_file = backup_ghost_files(config.ghost_path, config.backup_path, database_name)

    if not db_backup_file or not ghost_backup_file:
        print("\nBackup failed. Aborting the process.")
        return

    print(f"\nDatabase backed up to: {db_backup_file}")
    print(f"Ghost content backed up to: {ghost_backup_file}")

    # Step 2: Find and log images
    print("\n--- Step 2: Finding and logging images ---")
    all_images, duplicates = find_images(config.images_path, config.log_path, database_name)

    if not all_images:
        print("No images found to process. Aborting.")
        return

    # Step 3: Convert images to WebP
    print("\n--- Step 3: Converting images to WebP ---")
    conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name)

    if not conversion_map:
        print("Image conversion failed or produced no results. Aborting.")
        return

    print(f"Successfully converted {len(conversion_map)} images.")

    # Step 4: Backup plaintext from database
    print("\n--- Step 4: Backing up plaintext from database ---")
    plaintext_backup_file = backup_plaintext(config.db_config, config.backup_path)
    if plaintext_backup_file:
        print(f"Plaintext backed up to: {plaintext_backup_file}")

    # Step 5: Update image links in database
    print("\n--- Step 5: Updating image links in database (html, feature_image) ---")
    updated_count = update_image_links(config.db_config, conversion_map)
    if updated_count == -1:
        print("Failed to update database links. Check logs for errors. Aborting.")
        return

    # Step 6: Restore plaintext
    print("\n--- Step 6: Restoring original plaintext to database ---")
    restored_count = restore_plaintext(config.db_config, plaintext_backup_file)
    if restored_count == -1:
        print("Failed to restore plaintext. Manual check may be required.")

    print("\nProcess finished successfully!")

if __name__ == "__main__":
    main()