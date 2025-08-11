#!/bin/bash
mkdir -p /app/logs
chmod 777 /app/logs

# Save environment variables for cron
echo "NEO4J_URI=$NEO4J_URI" > /etc/environment
echo "NEO4J_USER=$NEO4J_USER" >> /etc/environment
echo "NEO4J_PASSWORD=$NEO4J_PASSWORD" >> /etc/environment

# Remove ALL existing crontabs
crontab -r 2>/dev/null || true

# Install crontab that sources the environment
echo '* * * * * . /etc/environment && /usr/local/bin/python /app/execute_automations.py >> /app/logs/automation.log 2>&1' | crontab -

# Verify
echo "Crontab entries:"
crontab -l
echo "Environment saved:"
cat /etc/environment

# Start cron
service cron start

# Start Flask API
exec /usr/local/bin/python /app/risk_api.py