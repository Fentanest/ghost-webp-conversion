# Overview

This project provides Python utilities for managing images in Ghost CMS.

- **main.py** — Converts all uploaded image files to WebP format and automatically updates the database references.
- **cleanup.py** — Scans the database to identify and remove unused image files, keeping your Ghost instance clean and efficient.

Check out [worklazy.net](https://worklazy.net) or [hb.worklazy.net](https://hb.worklazy.net) to see a blog that converted all images to WebP using this project.

<br>

# Instruction

## Caution

When running for the first time, use the `--dry﻿` option to preview the entire operation, and avoid using the `--nobackup﻿` option.

Make sure to verify that the correct values are set in `config.py﻿` before starting.

<br>

## Usage Instructions

1. Install pigz, mysqldump (also Python and venv if you don't have)
   - Debian / Ubuntu:
     ```
     sudo apt update
     sudo apt install mysql-client pigz
     sudo apt install python3 python3-venv
     ```
   - RHEL / CentOS / Fedora (YUM/DNF):
     ```
     sudo dnf install mariadb pigz
     sudo dnf install python3 python3-venv
     ```
   - openSUSE:
     ```
     sudo zypper install mariadb-client pigz
     sudo zypper install python3 python3-venv
     ```
   - Arch Linux:
     ```
     sudo pacman -S mariadb pigz
     sudo pacman -S python python-virtualenv
     ```
<br>

2. Clone Repo
```
git clone https://github.com/Fentanest/ghost-webp-conversion.git
cd ghost-webp-conversion
```
<br>

3. Define the following values in your `config.py` file:

```
nano config.py
```

| Key | Description |
|---|---|
| user | MySQL username (typically `root`) |
| host | MySQL host address |
| port | MySQL port (default 3306) |
| database | Name of your GhostCMS database |
| password | Password for the MySQL user |
| ghost_path | Absolute path to the Ghost `content` directory |
| images_path | Absolute path to the Ghost `images` directory |
| backup_path | Directory where backup files will be stored |
| log_path | Directory where log files will be saved |
| webp_quality | Desired quality level for WebP image conversion (range: 0–100) |

<br>

4. Set up a Python virtual environment
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
<br>

5. Execute WebP conversion process
```
python main.py
```

This process automatically creates a backup of the DB file and Content folder in the backup path.

Add `--dry` if you want to simulate the action without actually executing it.

If you want to take a risky one-way trip without backup, use `--nobackup`.

<br>

6. Perform cleanup of unused images
```
python cleanup.py
```

This process collects the images to be deleted and creates a compressed file in the backup path.

As with Step 5, you can use `--dry` and `--nobackup`.

<br>

7. Restart Ghost CMS

To apply the changes completely — including the logo, cover image, and icon — you need to restart your Ghost CMS instance.

<br>

---

### Recovery Guide

If any error occurs during execution, restore your GhostCMS using the automatically generated backup files located in the `backup` directory.

### About step 6

Review the **Image Cleanup List** carefully before proceeding.  
Type **yes** to confirm the operation.  
If something goes wrong during this step, use the `unused_images_backup_{database}...tar.gz` file from the `backup` directory to restore the images.
`tar -zxvf /path/to/backup/unused_images_backup_...tar.gz -C /`
