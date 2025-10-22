# backup.py
import argparse
import config
from db_handler import backup_database, verify_db_connection_or_abort
from file_handler import backup_ghost_files

def run_backup_process(dry_run=False, assume_yes=False):
    """
    Orchestrates the backup of the Ghost database and content files.
    Returns True on success, False on failure.
    """
    # Display current configuration and ask for user confirmation
    print("\n--- Current Configuration & Settings ---")
    print(f"Database Host: {config.db_config.get('host', 'N/A')}")
    print(f"Database Port: {config.db_config.get('port', 'N/A')}")
    print(f"Database Name: {config.db_config.get('database', 'N/A')}")
    print(f"Ghost Path: {config.ghost_path}")
    print(f"Backup Path: {config.backup_path}")
    print("---")
    print(f"Dry Run Mode: {'Yes' if dry_run else 'No'}")
    print("----------------------------------------")

    if not assume_yes:
        user_input = input("Do you want to proceed with the backup process based on these settings? (yes/no): ")
        if user_input.lower() != 'yes':
            print("Process aborted by user.")
            return False

    verify_db_connection_or_abort(config.db_config)

    database_name = config.db_config['database']

    print("\n--- Backing up database and files ---")
    db_backup_file = backup_database(config.db_config, config.backup_path, dry_run=dry_run)
    ghost_backup_file = backup_ghost_files(config.ghost_path, config.backup_path, database_name, dry_run=dry_run)

    # In dry_run, the backup functions return a simulated path or None, but we don't want to fail.
    if (not db_backup_file or not ghost_backup_file) and not dry_run:
        print("\nBackup failed. Please check the logs.")
        return False

    if db_backup_file:
        print(f"\nDatabase backed up to: {db_backup_file}")
    if ghost_backup_file:
        print(f"Ghost content backed up to: {ghost_backup_file}")
    
    print("\nBackup process finished successfully!")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backup utility for Ghost CMS database and content files.")
    parser.add_argument('--dry', action='store_true', help="Run in dry-run mode. No actual backups will be created.")
    args = parser.parse_args()

    if args.dry:
        print("--- Running in DRY RUN mode. No actual files will be created. ---\n")

    run_backup_process(dry_run=args.dry)
