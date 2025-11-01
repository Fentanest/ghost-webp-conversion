# Ghost Admin API configuration
# Found in Ghost Admin -> Integrations -> Custom Integrations
ghost_api_url = 'https://your-ghost-domain.com'  # e.g., https://blog.example.com
ghost_admin_api_key = 'your_admin_api_key'

# JWT token expiration time in minutes
jwt_expiration_minutes = 5

# MySQL database configuration
# NOTE: This is still required for backup.py and reorganize.py
db_config = {
    'user': 'your_mysql_user',
    'password': 'your_mysql_password',
    'host': 'your_mysql_host',
    'port': 3306,
    'database': 'your_mysql_database'
}

# Path to the Ghost CMS root directory
# Example: '/var/lib/ghost'
ghost_path = '/path/to/your/ghost'

# Absolute path to the Ghost CMS images directory
# Example: '/var/lib/ghost/content/images'
images_path = '/path/to/your/ghost/content/images'

# Absolute path to the Ghost CMS media directory
# Example: '/var/lib/ghost/content/media'
media_path = '/path/to/your/ghost/content/media'

# Path to store backup files
backup_path = '/path/to/your/backup/directory'

# Path to store log files
log_path = '/path/to/your/log/directory'

# WebP conversion quality (0-100)
webp_quality = 80
