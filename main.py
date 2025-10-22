# main.py
import config
from db_handler import verify_db_connection_or_abort, backup_plaintext, update_image_links, restore_plaintext
from file_handler import find_images, convert_images_to_webp
import argparse

def main(dry_run=False, nobackup=False):
    """Main function to run the conversion process."""
    # Step 0: Verify database connection before anything else
    verify_db_connection_or_abort(config.db_config)

    print("Starting the Ghost WebP conversion process...")

    # Display current configuration and ask for user confirmation
    print("\n--- Current Configuration & Settings ---")
    print(f"Database Host: {config.db_config.get('host', 'N/A')}")
    print(f"Database Port: {config.db_config.get('port', 'N/A')}")
    print(f"Database Name: {config.db_config.get('database', 'N/A')}")
    print(f"Ghost Path: {config.ghost_path}")
    print(f"Images Path: {config.images_path}")
    print(f"Backup Path: {config.backup_path}")
    print(f"Log Path: {config.log_path}")
    print(f"WebP Quality: {config.webp_quality}")
    print("---")
    print(f"Dry Run Mode: {'Yes' if dry_run else 'No'}")
    print(f"Skip Backups: {'Yes' if nobackup else 'No'}")
    print("----------------------------------------")

    user_input = input("Do you want to proceed with the process based on these settings? (yes/no): ")
    if user_input.lower() != 'yes':
        print("Process aborted by user.")
        return

    database_name = config.db_config['database']

    # --- Confirmation for --nobackup ---
    if nobackup and not dry_run: # Only ask if nobackup is true AND it's not a dry run
        print("\n--- WARNING: --nobackup option is active ---")
        print("You are about to proceed WITHOUT creating any backups (database, Ghost files, plaintext).")
        print("This means the process is IRREVERSIBLE if any errors occur.")
        user_input = input("Are you sure you want to proceed without backups? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Process aborted by user.")
            return
    # --- End Confirmation ---

    # Step 1: Backup
    if not nobackup:
        from backup import run_backup_process
        if not run_backup_process(dry_run=dry_run, assume_yes=True):
            # The run_backup_process function prints its own errors.
            # We just need to abort the main script if it fails.
            if not dry_run:
                print("\nBackup step failed. Aborting the main process.")
                return
            else:
                print("\nDRY RUN: Backup step would have failed.")
    else:
        print("Skipping database and Ghost file backup as per --nobackup option.")

    # Step 2: Find and log images
    print("\n--- Step 2: Finding and logging images ---")
    all_images, duplicates = find_images(config.images_path, config.log_path, database_name)

    if not all_images:
        print("No images found to process. Aborting.")
        return

    # Step 3: Convert images to WebP
    print("\n--- Step 3: Converting images to WebP ---")
    conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name, dry_run=dry_run)

    if not conversion_map:
        print("Image conversion failed or produced no results. Aborting.")
        return

    print(f"Successfully converted {len(conversion_map)} images.")

    # Step 4: Backup plaintext from database
    print("\n--- Step 4: Backing up plaintext from database ---")
    plaintext_backup_file = None
    # This call should always happen, regardless of --nobackup, as it's needed for restoration
    plaintext_backup_file = backup_plaintext(config.db_config, config.backup_path, dry_run=dry_run) # Pass dry_run
    if plaintext_backup_file:
        print(f"Plaintext backed up to: {plaintext_backup_file}")
    # Removed the 'else' block for skipping plaintext backup

    # Step 5: Update image links in database
    print("\n--- Step 5: Updating image links in database (posts and settings) ---")
    updated_posts, updated_settings = update_image_links(config.db_config, conversion_map, dry_run=dry_run, log_path=config.log_path, database_name=database_name)
    if updated_posts == -1 or updated_settings == -1:
        print("Failed to update database links. Check logs for errors. Aborting.")
        return

    # Step 6: Restore plaintext
    print("\n--- Step 6: Restoring original plaintext to database ---")
    restored_count = restore_plaintext(config.db_config, plaintext_backup_file, dry_run=dry_run)
    if restored_count == -1:
        print("Failed to restore plaintext. Manual check may be required.")

    print("\nProcess finished successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Ghost CMS images to WebP and update database links.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No actual conversions or database updates will be performed.")
    parser.add_argument('--nobackup', action='store_true', help="Skip all backup processes (database, Ghost files, plaintext). Use with caution!")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No actual conversions or database updates will be performed. ---\n")
    if args.nobackup:
        print("--- Running with --nobackup option. All backup processes will be skipped. ---")

    main(dry_run=args.dry, nobackup=args.nobackup)
