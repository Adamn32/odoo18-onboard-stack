#!/bin/bash

# Define variables
BACKUP_DIR="/path/to/backup/directory"  # You can set this to another directory or leave it as is
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
DB_NAME="your_odoo_db"   # Adjust this with your actual Odoo database name
DB_USER="your_db_user"   # Adjust this with your database username
DB_PASSWORD="your_db_password"  # Adjust this with your database password
DB_HOST="localhost"
DB_PORT="5432"

# Set the environment for PostgreSQL
export PGPASSWORD=$DB_PASSWORD

# Create backup directory if it does not exist
mkdir -p $BACKUP_DIR

# Backup PostgreSQL database
pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER $DB_NAME > $BACKUP_DIR/odoo_db_backup_$DATE.sql

# Backup Odoo filestore
tar -czvf $BACKUP_DIR/odoo_filestore_backup_$DATE.tar.gz ~/odoo18-onboard-stack/odoo/filestore

# Optional: Remove backups older than 30 days
find $BACKUP_DIR -type f -name "*.sql" -mtime +30 -exec rm -f {} \;
find $BACKUP_DIR -type f -name "*.tar.gz" -mtime +30 -exec rm -f {} \;

# Notify via email (Optional)
echo "Odoo Backup Completed: $DATE" | mail -s "Odoo Backup Status" your_email@example.com
