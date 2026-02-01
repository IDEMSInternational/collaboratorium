# NextCloud App Hooks

This directory contains scripts that automatically configure NextCloud on startup.

## Directory Structure

- `post-init.d/` - Scripts run after NextCloud initialization but before it becomes accessible

## Hook Execution

Scripts in `post-init.d/` are executed in alphabetical order:
- `10-enable-groupfolders.sh` - Enables the GroupFolders app for collaborative document storage
- `15-configure-collabora.sh` - Configures NextCloud Office to use Collabora Online server

## Adding New Hooks

To add new configuration steps:

1. Create a new shell script in the appropriate directory (e.g., `post-init.d/20-my-config.sh`)
2. Make it executable: `chmod +x nextcloud_hooks/post-init.d/20-my-config.sh`
3. The script will automatically run on next container initialization

## How It Works

The `nextcloud_hooks` directory is mounted into the NextCloud container at `/docker-entrypoint-init.d/`, which is part of the official NextCloud Docker image's initialization process.

When the container starts:
1. NextCloud initializes normally
2. All scripts in mounted hook directories are executed in order
3. Our scripts enable required apps and configure settings

## Important Notes

- Scripts run as the web server user (www-data)
- They have access to the `occ` command-line tool
- Changes persist in the NextCloud data volume
- Hooks are idempotent - safe to run multiple times
