#!/bin/bash
mkdir -p /app/logs
chmod 777 /app/logs

# Install crontab from file
crontab /app/crontab

# Verify
echo "Crontab entries:"
crontab -l

# Start cron
service cron start

# Start Flask API
exec /usr/local/bin/python /app/risk_api.py