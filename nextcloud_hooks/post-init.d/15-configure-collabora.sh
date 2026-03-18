#!/bin/bash
# Configure NextCloud Office (richdocuments) with Collabora Online server
# This hook runs after NextCloud is initialized but before it becomes available to users

set -e

COLLABORA_URL="https://collabora.${DOMAIN:?}"

echo "Configuring NextCloud Office with Collabora server..."

# Enable richdocuments (NextCloud Office) app if not already enabled
php /var/www/html/occ app:enable richdocuments || echo "NextCloud Office app already enabled"

# Configure the WOPI server URL
# This tells NextCloud Office where the Collabora server is located
php /var/www/html/occ config:app:set richdocuments wopi_url --value="${COLLABORA_URL}" || echo "WOPI URL already configured"
php /var/www/html/occ config:app:set richdocuments disable_certificate_verification --value="yes"

echo "NextCloud Office is now configured to use Collabora server at ${COLLABORA_URL}"
