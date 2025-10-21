# main.py
import config
from db_handler import backup_database, backup_plaintext, update_image_links, restore_plaintext
from file_handler import backup_ghost_files, find_images, convert_images_to_webp
import argparse

def main(dry_run=False, nobackup=False):
    """Main function to run the conversion process."""
    print("Starting the Ghost WebP conversion process...")

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
    print("\n--- Step 1: Backing up database and files ---")
    db_backup_file = None
    ghost_backup_file = None
    if not nobackup:
        db_backup_file = backup_database(config.db_config, config.backup_path, nobackup=nobackup, dry_run=dry_run) # Pass dry_run
        ghost_backup_file = backup_ghost_files(config.ghost_path, config.backup_path, database_name, nobackup=nobackup, dry_run=dry_run) # Pass dry_run

        if not db_backup_file or not ghost_backup_file:
            if not dry_run: # Only abort if not dry_run and backup actually failed
                print("\nBackup failed. Aborting the process.")
                return
            else: # In dry_run, just print a warning
                print("\nDRY RUN: Backup would have failed or been skipped.")


        if db_backup_file: # Only print if backup was actually performed/simulated
            print(f"\nDatabase backed up to: {db_backup_file}")
        if ghost_backup_file: # Only print if backup was actually performed/simulated
            print(f"Ghost content backed up to: {ghost_backup_file}")
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
    print("\n--- Step 5: Updating image links in database (html, feature_image) ---")
    updated_count = update_image_links(config.db_config, conversion_map, dry_run=dry_run, log_path=config.log_path, database_name=database_name) # Pass log_path and database_name
    if updated_count == -1:
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
        print("--- Running with --nobackup option. All backup processes will be skipped. ---\n")

    main(dry_run=args.dry, nobackup=args.nobackup)