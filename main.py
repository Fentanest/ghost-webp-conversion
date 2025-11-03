# main.py
import config
from api_handler import update_image_links_via_api
from file_handler import find_images, convert_images_to_webp
import argparse
from datetime import datetime

def main(dry_run=False, nobackup=False, assume_yes=False):
    """Main function to run the conversion process using the Ghost API."""
    print("Starting the Ghost WebP conversion process...")

    database_name = config.db_config.get('database', 'ghost')

    # --- Step 1: Analysis Phase ---
    print("\n--- Step 1: Analyzing Images and Creating Conversion Plan ---")
    print("Finding and logging images...")
    all_images, duplicates = find_images(config.images_path, config.log_path, database_name)

    if not all_images:
        print("No images found to process. Aborting.")
        return

    print("Generating conversion map (Dry Run)...")
    conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name, config.ghost_api_url, dry_run=True)

    if not conversion_map:
        print("Image conversion analysis failed or produced no results. Aborting.")
        return

    import json
    import os
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    map_log_path = os.path.join(config.log_path, f"conversion_map_{database_name}_{timestamp}.json")
    print(f"Saving conversion plan to: {map_log_path}")
    with open(map_log_path, 'w', encoding='utf-8') as f:
        json.dump(conversion_map, f, indent=2, ensure_ascii=False)

    # --- Confirmation Prompt ---
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
    print(f"Analysis complete. Found {len(conversion_map) // 3} images to convert and update.")
    print(f"The detailed conversion plan has been saved to: {map_log_path}")

    if not assume_yes:
        user_input = input("Do you want to proceed with the full process based on this plan? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Process aborted by user.")
            return
    else:
        print("Bypassing prompt due to --yes flag.")

    # --- Execution Starts ---
    if nobackup and not dry_run:
        print("\n--- WARNING: --nobackup option is active ---")
        if not assume_yes:
            user_input = input("Are you sure you want to proceed without backups? (yes/no): ")
            if user_input.lower() != 'yes':
                print("Process aborted by user.")
                return
        else:
            print("Bypassing prompt due to --yes flag.")

    # Step 2: Backup
    if not nobackup:
        print("\n--- Step 2: Backing up database and files ---")
        from backup import run_backup_process
        if not run_backup_process(dry_run=dry_run, assume_yes=True):
            if not dry_run:
                print("\nBackup step failed. Aborting the main process.")
                return
            else:
                print("\nDRY RUN: Backup step would have failed.")
    else:
        print("\n--- Step 2: Backing up database and files (SKIPPED) ---")

    # Step 3: Convert images to WebP (Execution Phase)
    if not dry_run:
        print("\n--- Step 3: Converting images to WebP (Execution Phase) ---")
        conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name, config.ghost_api_url, dry_run=False)
        print(f"Successfully converted {len(conversion_map) // 3} images.")
    else:
        print("\n--- Step 3: Converting images to WebP (DRY RUN) ---")
        print(f"DRY RUN: No actual conversion will be performed.")

    # Step 4: Update image links via Ghost Admin API
    print("\n--- Step 4: Updating image links via Ghost Admin API ---")
    updated_posts, _ = update_image_links_via_api(conversion_map, dry_run=dry_run, log_path=config.log_path, database_name=database_name)
    if updated_posts == -1:
        print("Failed to update content via API. Check logs for errors. Aborting.")
        return

    print("\nProcess finished successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Ghost CMS images to WebP and update content via Admin API.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No actual conversions or API updates will be performed.")
    parser.add_argument('--nobackup', action='store_true', help="Skip all backup processes. Use with caution!")
    parser.add_argument('--yes', action='store_true', help="Bypass all interactive prompts and proceed automatically.")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No actual conversions or API updates will be performed. ---\n")
    if args.nobackup:
        print("--- Running with --nobackup option. All backup processes will be skipped. ---")

    main(dry_run=args.dry, nobackup=args.nobackup, assume_yes=args.yes)
