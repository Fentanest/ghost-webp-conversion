# Instruction
---
### Configuration

Define the following values in your `config.py` file:

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

---

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

3. Set up a Python virtual environment
```
python3 -m venv venv
source venv/bin/activate
```

4. Install required dependencies
```
pip install -r requirements.txt
```

5. Execute WebP conversion process
```
python main.py
```

6. Perform cleanup of unused images
```
python cleanup.py
```

Review the list of images to be deleted and type 'yes' exactly to confirm deletion of image files.

If an error occurs during step 6, restore from the generated backup archive located in the backup folder path, named unused_images_backup_{database}...tar.gz.
