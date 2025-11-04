# main.py
import config
from api_handler import update_image_links_via_api, get_image_urls_from_published_content
from file_handler import convert_images_to_webp, resolve_urls_to_local_paths
import argparse
from datetime import datetime
import json
import os

def find_duplicates_from_list(image_paths, log_path, database_name, timestamp):
    """Finds and logs duplicate basenames from a given list of image paths."""
    duplicate_files_log_path = os.path.join(log_path, f"duplicate_files_{database_name}_{timestamp}.log")
    basenames = {}
    for image_path in image_paths:
        basename, _ = os.path.splitext(image_path)
        if basename not in basenames:
            basenames[basename] = []
        basenames[basename].append(image_path)

    duplicates = {base: paths for base, paths in basenames.items() if len(paths) > 1}

    if duplicates:
        print(f"Found {len(duplicates)} sets of files with duplicate names.")
        with open(duplicate_files_log_path, 'w') as f:
            for basename, paths in duplicates.items():
                f.write(f"Basename: {basename}\n")
                for path in paths:
                    f.write(f"  - {path}\n")
        print(f"List of duplicate-named files saved to: {duplicate_files_log_path}")
    
    return duplicates

def main(dry_run=False, nobackup=False, assume_yes=False, timestamp=None):
    """Main function to run the conversion process using the Ghost API."""
    if not timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("Starting the Ghost WebP conversion process...")

    database_name = config.db_config.get('database', 'ghost')

    # --- Step 1: Analysis Phase ---
    print("\n--- Step 1: Analyzing Images and Creating Conversion Plan ---")
    
    # 1a. Get all image URLs from published/scheduled content
    image_urls = get_image_urls_from_published_content()
    if not image_urls:
        print("No image URLs found in published content. Aborting.")
        return

    # 1b. Resolve URLs to local file paths
    all_images = resolve_urls_to_local_paths(image_urls, config.images_path, config.ghost_api_url)
    if not all_images:
        print("No local image files were found from the URLs. Aborting.")
        return

    # 1c. Find duplicates among the resolved images
    duplicates = find_duplicates_from_list(all_images, config.log_path, database_name, timestamp)

    print("Generating conversion map (Dry Run)...")
    conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name, config.ghost_api_url, timestamp, dry_run=True)

    if not conversion_map:
        print("Image conversion analysis failed or produced no results. Aborting.")
        return

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
        if not run_backup_process(dry_run=dry_run, assume_yes=True, timestamp=timestamp):
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
        conversion_map = convert_images_to_webp(all_images, duplicates, config.webp_quality, config.log_path, config.images_path, database_name, config.ghost_api_url, timestamp, dry_run=False)
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

    execution_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    main(dry_run=args.dry, nobackup=args.nobackup, assume_yes=args.yes, timestamp=execution_timestamp)
