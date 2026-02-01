#!/bin/bash
# Enable GroupFolders app and create collaborative group folder for Collaboratorium
# This hook runs after NextCloud is initialized but before it becomes available to users

set -e

echo "Installing and configuring GroupFolders app..."

# Enable the groupfolders app if not already enabled
php /var/www/html/occ app:enable groupfolders || echo "GroupFolders app already enabled"

# Create a group folder for collaborative document storage
# The --groups parameter is optional here; you can manage group membership via the UI
php /var/www/html/occ groupfolders:create collaboratorium || echo "Group folder 'collaboratorium' already exists"

echo "GroupFolders app is now enabled and ready to use"
