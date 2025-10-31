# main.py
import config
from api_handler import update_image_links_via_api
from file_handler import find_images, convert_images_to_webp
import argparse

def main(dry_run=False, nobackup=False):
    """Main function to run the conversion process using the Ghost API."""
    print("Starting the Ghost WebP conversion process...")

    # Display current configuration and ask for user confirmation
    print("\n--- Current Configuration & Settings ---")
    print(f"Ghost API URL: {config.ghost_api_url}")
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

    # Still needed for log file naming, get it safely.
    database_name = config.db_config.get('database', 'ghost')

    # --- Confirmation for --nobackup ---
    if nobackup and not dry_run:
        print("\n--- WARNING: --nobackup option is active ---")
        print("You are about to proceed WITHOUT creating any backups.")
        print("This means the process is IRREVERSIBLE if any errors occur.")
        user_input = input("Are you sure you want to proceed without backups? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Process aborted by user.")
            return
    # --- End Confirmation ---

    # Step 1: Backup (No changes here, still uses file/db backup)
    if not nobackup:
        from backup import run_backup_process
        if not run_backup_process(dry_run=dry_run, assume_yes=True):
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
    conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name, config.ghost_api_url, dry_run=dry_run)

    if not conversion_map:
        print("Image conversion failed or produced no results. Aborting.")
        return

    print(f"Successfully converted {len(conversion_map) // 3} images.")

    # Save the conversion map to a file for debugging
    import json
    import os
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    map_log_path = os.path.join(config.log_path, f"conversion_map_{database_name}_{timestamp}.json")
    print(f"\nSaving conversion map to: {map_log_path}")
    with open(map_log_path, 'w', encoding='utf-8') as f:
        json.dump(conversion_map, f, indent=2, ensure_ascii=False)

    # Step 4: Update image links in database via API
    print("\n--- Step 4: Updating image links via Ghost Admin API ---")
    updated_posts, updated_settings = update_image_links_via_api(conversion_map, dry_run=dry_run, log_path=config.log_path, database_name=database_name)
    if updated_posts == -1 or updated_settings == -1:
        print("Failed to update content via API. Check logs for errors. Aborting.")
        return

    print("\nProcess finished successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Ghost CMS images to WebP and update content via Admin API.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No actual conversions or API updates will be performed.")
    parser.add_argument('--nobackup', action='store_true', help="Skip all backup processes. Use with caution!")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No actual conversions or API updates will be performed. ---\n")
    if args.nobackup:
        print("--- Running with --nobackup option. All backup processes will be skipped. ---")

    main(dry_run=args.dry, nobackup=args.nobackup)
