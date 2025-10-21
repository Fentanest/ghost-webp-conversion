# Instruction

### Usage Instructions

1. Install pigz, mysqldump
   - Debian / Ubuntu:
     ```
     sudo apt update
     sudo apt install mysql-client pigz
     ```
   - RHEL / CentOS / Fedora (YUM/DNF):
     ```
     sudo dnf install mariadb pigz
     ```
   - openSUSE:
     ```
     sudo zypper install mariadb-client pigz
     ```
   - Arch Linux:
     ```
     sudo pacman -S mariadb pigz
     ```

2. Clone Repo
```
git clone https://github.com/Fentanest/ghost-webp-conversion.git
cd ghost-webp-conversion
```

3. Define the following values in your `config.py` file:
```
nano config.py
```

| Key | Description |
|---|---|
| user | MySQL username (typically `root`) |
| host | MySQL host address |
| database | Name of your GhostCMS database |
| password | Password for the MySQL user |
| ghost_path | Absolute path to the Ghost `content` directory |
| images_path | Absolute path to the Ghost `images` directory |
| backup_path | Directory where backup files will be stored |
| log_path | Directory where log files will be saved |
| webp_quality | Desired quality level for WebP image conversion (range: 0–100) |

4. Set up a Python virtual environment
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

5. Execute WebP conversion process
```
python main.py
```

If you want to see what happens, add `--dry`

This process automatically creates a backup of the DB file and Content folder in the backup path.

If you want to take a risky one-way trip without backup, use `--nobackup`.

6. Perform cleanup of unused images
```
python cleanup.py
```

This process collects the images to be deleted and creates a compressed file in the backup path.

As with Step 5, you can use `--dry` and `--nobackup`.

### Recovery Guide

If any error occurs during execution, restore your GhostCMS using the automatically generated backup files located in the `backup` directory.

### About step 6

Review the **Image Cleanup List** carefully before proceeding.  
Type **yes** to confirm the operation.  
If something goes wrong during this step, use the `unused_images_backup_{database}...tar.gz` file from the `backup` directory to restore the images.
`tar -zxvf /path/to/backup/unused_images_backup_...tar.gz -C /`
