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
```

5. Install required dependencies
```
pip install -r requirements.txt
```

6. Execute WebP conversion process
```
python main.py
```

7. Perform cleanup of unused images
```
python cleanup.py
```

---

### Recovery Guide

If any error occurs during execution, restore your GhostCMS using the automatically generated backup files located in the `backup` directory.

### Step 7

Review the **Image Cleanup List** carefully before proceeding.  
Type **yes** to confirm the operation.  
If something goes wrong during this step, use the `unused_images_backup_{database}...tar.gz` file from the `backup` directory to restore the images.

