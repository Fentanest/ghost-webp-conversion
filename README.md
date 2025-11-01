# Ghost CMS Image Management Utilities

This project provides a suite of Python utilities designed to help you efficiently manage the images in your Ghost CMS instance.

- **`main.py`**: Converts all uploaded images to the modern, efficient WebP format and automatically updates all database references to point to the new files.
- **`reorganize.py`**: Organizes your media files into structured, slug-based folders, making your content directory easier to navigate and manage.
- **`cleanup.py`**: Scans your Ghost database to identify and remove unused, orphaned images, freeing up storage space and keeping your instance tidy.
- **`alt.py`**: Automatically generates and updates `alt` tags for images in your Ghost posts, improving SEO and accessibility.

These tools are designed to be run in the command line and offer options for dry runs and backups to ensure safe operation.

Check out [worklazy.net](https://worklazy.net) or [hb.worklazy.net](https://hb.worklazy.net) to see a blog that converted all images to WebP using this project.

<br>

# Instructions

## ⚠️ Important Precautions

- **Always back up your data before running any scripts.** Although the tools include backup features, manual backups provide an extra layer of security.
- When running a script for the first time, use the `--dry` option. This will simulate the entire process and show you what changes would be made without actually modifying any files.
- Avoid using the `--nobackup` option unless you are certain you will not need to restore any data.
- Before starting, double-check that all values in `config.py` are correctly set for your environment.

<br>

## ⚙️ Usage Instructions

### 1. Install Prerequisites
You will need `pigz` for faster compression and `mysqldump` for database backups.

- **Debian / Ubuntu:**
  ```bash
  sudo apt update
  sudo apt install mysql-client pigz python3 python3-venv
  ```
- **RHEL / CentOS / Fedora:**
  ```bash
  sudo dnf install mariadb pigz python3 python3-venv
  ```
- **openSUSE:**
  ```bash
  sudo zypper install mariadb-client pigz python3 python3-venv
  ```
- **Arch Linux:**
  ```bash
  sudo pacman -S mariadb-clients pigz python python-virtualenv
  ```

### 2. Clone the Repository
```bash
git clone https://github.com/Fentanest/ghost-webp-conversion.git
cd ghost-webp-conversion
```

### 3. Configure Your Settings
Open `config.py` and define the required values.

```bash
nano config.py
```

| Key | Description |
|---|---|
| `user` | MySQL username (typically `root`). |
| `host` | MySQL host address. |
| `port` | MySQL port (default is `3306`). |
| `database` | The name of your Ghost CMS database. |
| `password` | The password for the MySQL user. |
| `ghost_path` | The absolute path to your Ghost `content` directory. |
| `images_path` | The absolute path to your Ghost `images` directory. |
| `media_path` | The absolute path to your Ghost `media` directory. |
| `backup_path` | The directory where backup files will be stored. | 
| `log_path` | The directory where log files will be saved. |
| `webp_quality` | The desired quality for WebP conversion (0–100). |
| `ghost_api_url` | The URL of your Ghost site (e.g., `https://your.blog.com`). |
| `ghost_admin_api_key` | Your Ghost Admin API Key for authentication. |

### 4. Set Up a Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Run the Scripts

#### Convert Images to WebP
```bash
python main.py [--dry] [--nobackup]
```
This script converts images and creates backups of your database and content folder in the `backup_path`.
- Use `--dry` to simulate the conversion and see what changes would be made without actually modifying any files.
- Use `--nobackup` to skip the backup process.

#### Reorganize Media Files
```bash
python reorganize.py [--dry]
```
This script moves your images and media into slug-based subdirectories. It generates a `reorganization_map_*.json` file to track changes. It will ask for user confirmation before moving files.
- Use `--dry` to simulate the reorganization and see what changes would be made without actually moving any files or updating the API.

#### Clean Up Unused Images
```bash
python cleanup.py [--dry] [--nobackup]
```
This script finds and deletes unused images. It creates a compressed backup of the deleted files. It also generates `used_images_from_api_*.json` and `unused_images_to_delete_*.json` for your review.
- Use `--dry` to simulate the cleanup and see which files would be deleted without actually deleting them or creating a backup.
- Use `--nobackup` to skip the backup process for deleted files.

#### Update Image Alt Tags
```bash
python alt.py [--dry] [--force]
```
This script automatically populates missing `alt` tags for images in your posts using their filenames. 
- Use `--dry` to see which `alt` tags would be added/updated without making any changes.
- Use `--force` to overwrite existing `alt` tags, even if they are already present.

### 6. Restart Ghost CMS
To ensure all changes are applied—especially for site-wide images like logos and icons—restart your Ghost instance.

<br>

---

## 📄 Generated Log Files

The scripts generate various log files in the `log_path` directory, which are crucial for debugging, tracking changes, and understanding script operations.

### JSON Log Files:

- **`conversion_map_ghost_*.json`**: Generated by `main.py`, this file maps the original image paths to their newly converted WebP paths. It's used to update the Ghost database.
- **`used_images_from_api_*.json`**: A list of all image paths that `cleanup.py` detected as being in use by your Ghost site, fetched directly from the Ghost API.
- **`unused_images_to_delete_*.json`**: A list of the absolute paths of all images that `cleanup.py` has identified as unused and marked for deletion.
- **`reorganization_map_*.json`**: A comprehensive mapping created by `reorganize.py` that shows the old and new paths for every file it moves. This is essential for the API update process.
- **`alt_tags_log_*.json`**: A log generated by `alt.py` detailing all proposed or executed `alt` tag changes, including the post slug, image source, old alt text, and new alt text.

### Other Log Files:

- **`unused_files_log_*.log`**: A plain text log generated by `cleanup.py` listing the absolute paths of files that were identified as unused and either backed up or deleted.
- **`api_detailed_debug_ghost.log`**: A general debug log for API interactions, providing detailed information about requests and responses made to the Ghost API.
- **`url_debug_log.log`**: A debug log specifically for URL parsing and processing, useful for troubleshooting issues related to image path identification.

## ↩️ Recovery Guide

If an error occurs, you can restore your Ghost instance using the backup files created in the `backup_path`:
- **Database**: Restore the `.sql.gz` file to MySQL.
- **Content**: The `content_backup_...tar.gz` contains your `images` and `media` folders.
- **Deleted Images**: If you need to restore images deleted by `cleanup.py`, use the `unused_images_backup_...tar.gz` file. You can extract it to your content path with:
  ```bash
  tar -zxvf /path/to/backup/unused_images_backup_...tar.gz -C /
  ```
