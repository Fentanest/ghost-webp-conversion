import os

# Ghost Admin API configuration
# Found in Ghost Admin -> Integrations -> Custom Integrations
ghost_api_url = os.getenv('GHOST_API_URL', 'https://your-ghost-domain.com')  # e.g., https://blog.example.com
ghost_admin_api_key = os.getenv('GHOST_ADMIN_API_KEY', 'your_admin_api_key')

# JWT token expiration time in minutes
jwt_expiration_minutes = int(os.getenv('JWT_EXPIRATION_MINUTES', 5))

# MySQL database configuration
# NOTE: This is still required for backup.py and reorganize.py
db_config = {
    'user': os.getenv('DB_USER', 'your_mysql_user'),
    'password': os.getenv('DB_PASSWORD', 'your_mysql_password'),
    'host': os.getenv('DB_HOST', 'your_mysql_host'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'database': os.getenv('DB_DATABASE', 'your_mysql_database')
}

# Path to the Ghost CMS root directory
# Example: '/var/lib/ghost'
ghost_path = os.getenv('GHOST_PATH', '/path/to/your/ghost')

# Absolute path to the Ghost CMS images directory
# Example: '/var/lib/ghost/content/images'
images_path = os.getenv('IMAGES_PATH', '/path/to/your/ghost/content/images')

# Absolute path to the Ghost CMS media directory
# Example: '/var/lib/ghost/content/media'
media_path = os.getenv('MEDIA_PATH', '/path/to/your/ghost/content/media')

# Path to store backup files
backup_path = os.getenv('BACKUP_PATH', '/path/to/your/backup/directory')

# Path to store log files
log_path = os.getenv('LOG_PATH', '/path/to/your/log/directory')

# WebP conversion quality (0-100)
webp_quality = int(os.getenv('WEBP_QUALITY', 80))
