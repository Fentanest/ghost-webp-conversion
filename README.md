# Ghost CMS Image Management Utilities

This project provides a suite of Python utilities designed to help you efficiently manage the images in your Ghost CMS instance.

- **`main.py`**: Converts all uploaded images to the modern, efficient WebP format and automatically updates all database references to point to the new files.
- **`reorganize.py`**: Organizes your media files into structured, slug-based folders, making your content directory easier to navigate and manage.
- **`cleanup.py`**: Scans your Ghost **API** to identify images currently in use, then compares this with images on disk to find and remove unused, orphaned images, freeing up storage space and keeping your instance tidy.
- **`alt.py`**: Automatically generates and updates `alt` tags for images in your Ghost posts, improving SEO and accessibility.

**Note on Database Interaction:** Most scripts primarily interact with your Ghost instance via its Admin API. This API, in turn, manages the Ghost database. The `backup.py` script is the main utility that directly interacts with the MySQL database using `mysqldump` for full database backups.

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
| `jwt_expiration_minutes` | The expiration time for JWT tokens in minutes (default is 5). |

### 4. Set Up a Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Run the Scripts

#### Convert Images to WebP
```bash
python main.py [--dry] [--nobackup] [--yes]
```
This script converts images and creates backups of your database and content folder in the `backup_path`.
- Use `--dry` to simulate the conversion and see what changes would be made without actually modifying any files.
- Use `--nobackup` to skip the backup process.
- Use `--yes` to bypass interactive prompts and proceed automatically.

#### Reorganize Media Files
```bash
python reorganize.py [--dry] [--restore MAP_FILE] [--yes]
```
This script moves your images and media into slug-based subdirectories.
- Use `--dry` to simulate the reorganization without moving files or updating the API.
- Use `--restore MAP_FILE` to revert the changes using a `reorganization_map_*.json` file.
- Use `--yes` to bypass interactive prompts.

#### Clean Up Unused Images
```bash
python cleanup.py [--dry] [--nobackup] [--yes]
```
This script finds and deletes unused images and creates a compressed backup.
- Use `--dry` to see which files would be deleted without actually deleting them.
- Use `--nobackup` to skip the backup process.
- Use `--yes` to bypass interactive prompts.

#### Update Image Alt Tags
```bash
python alt.py [--dry] [--force] [--restore LOG_FILE] [--yes]
```
This script automatically populates missing `alt` tags for images.
- Use `--dry` to see which `alt` tags would be added/updated.
- Use `--force` to overwrite existing `alt` tags.
- Use `--restore LOG_FILE` to revert alt tag changes using an `alt_tags_log_*.json` file.
- Use `--yes` to bypass interactive prompts.

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
- **`reorganization_map_*.json`**: A comprehensive mapping created by `reorganize.py` that shows the old and new paths for every file it moves. This is essential for the API update process and for restoring changes.
- **`alt_tags_log_*.json`**: A log generated by `alt.py` detailing all proposed or executed `alt` tag changes. This file is required to restore alt tags to their previous state.

### Other Log Files:

- **`unused_files_log_*.log`**: A plain text log generated by `cleanup.py` listing the absolute paths of files that were identified as unused and either backed up or deleted.
- **`api_detailed_debug_ghost.log`**: A general debug log for API interactions, providing detailed information about requests and responses made to the Ghost API.
- **`url_debug_log.log`**: A debug log specifically for URL parsing and processing, useful for troubleshooting issues related to image path identification.

## ↩️ Recovery and Restore Guide

### Manual Recovery
If a script fails, you can manually restore your Ghost instance using the backup files from the `backup_path`:
- **Database**: Restore the `.sql.gz` file to MySQL.
- **Content**: The `content_backup_...tar.gz` contains your `images` and `media` folders.
- **Deleted Images**: To restore images deleted by `cleanup.py`, use the `unused_images_backup_...tar.gz` file:
  ```bash
  tar -zxvf /path/to/backup/unused_images_backup_...tar.gz -C /
  ```

### Automated Restore with `--restore`
The `reorganize.py` and `alt.py` scripts include a `--restore` flag that allows you to automatically revert changes using the JSON log files they generate.

#### Restoring Reorganization
To undo a file reorganization, run `reorganize.py` with the `--restore` flag, pointing to the corresponding `reorganization_map_*.json` file. This will move files back to their original locations and update the database references.

```bash
python reorganize.py --restore /path/to/logs/reorganization_map_20231027_123456.json
```

#### Restoring Alt Tags
To revert alt tag changes, run `alt.py` with the `--restore` flag and the path to the `alt_tags_log_*.json` file that was generated during the initial run.

```bash
python alt.py --restore /path/to/logs/alt_tags_log_20231027_123456.json
```


<br>

# Running with Docker

The easiest way to run this project is by using Docker Compose and the pre-built image from Docker Hub. All configuration is handled in a single `.env` file.

### 1. Prerequisites
- Docker and Docker Compose installed on your system.

### 2. Configure Your Environment
This project uses a `.env` file to manage all user-specific settings.

First, copy the provided example file:
```bash
cp .env.example .env
```

Next, open the `.env` file with a text editor and fill in the values for your environment. You **must** provide the absolute paths for the three `HOST_..._PATH` variables.

```
# .env file
# ----------------------------------------------------
# Docker Volume Paths
# ----------------------------------------------------
# IMPORTANT: You must provide the ABSOLUTE paths to the directories on your host machine.
# Example: /home/user/ghost_project/content
HOST_GHOST_CONTENT_PATH=/path/to/your/ghost/content
HOST_BACKUP_PATH=/path/to/your/backup/directory
HOST_LOG_PATH=/path/to/your/log/directory

# ----------------------------------------------------
# Ghost Admin API
# ----------------------------------------------------
GHOST_API_URL=https://your-ghost-domain.com
GHOST_ADMIN_API_KEY=your_admin_api_key

# ----------------------------------------------------
# Database Connection
# ----------------------------------------------------
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_HOST=your_mysql_host
DB_PORT=3306
DB_DATABASE=your_mysql_database

# ----------------------------------------------------
# Script Settings
# ----------------------------------------------------
JWT_EXPIRATION_MINUTES=5
WEBP_QUALITY=80

# ----------------------------------------------------
# Container Timezone
# ----------------------------------------------------
# Example: America/New_York, Europe/London, Asia/Seoul
TZ=Asia/Seoul
```
**Important:** For database settings, `DB_HOST` should point to your MySQL server's IP address accessible from Docker (e.g., `host.docker.internal` if running Docker Desktop, or the server's network IP).

### 3. Run with Docker Compose
Once your `.env` file is configured, navigate to the project root directory and run Docker Compose:

```bash
docker-compose up -d
```
This command will pull the `fentanest/ghost-webp-converter:latest` image, read your `.env` file, and start the container in the background.

To view the container's logs, you can run:
```bash
docker-compose logs -f
```

### 4. Executing Scripts within the Container
With the container running, you can execute any of the scripts using `docker exec`:

```bash
docker exec -it ghost-webp-converter python main.py --dry
docker exec -it ghost-webp-converter python reorganize.py
# etc.
```

### Building the Image Manually (Optional)
If you wish to build the image yourself instead of using the pre-built one, you can use the provided `build.sh` script. This requires you to be logged into Docker Hub.

To build a production image with versioning:
```bash
./build.sh
```
This will build and push a multi-platform image, tag it with `:latest` and a new version number (from the `VERSION` file), and then increment the version in the `VERSION` file.

To build a development image:
```bash
./build.sh --dev
```
This will build and push an image tagged only with `:dev`, without affecting the project version.
