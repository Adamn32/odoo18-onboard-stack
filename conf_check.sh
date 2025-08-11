#!/bin/bash
# Filename: check_unnecessary_confs.sh
# Description: This script checks for unnecessary .conf files in the Odoo stack

# Function to check if a file exists and is a .conf file
check_conf_file() {
    local conf_file=$1
    if [ -f "$conf_file" ]; then
        echo "Found: $conf_file"
    else
        echo "Not found: $conf_file"
    fi
}

# List of conf files that should be checked
conf_files=(
    "conf.d/comm.savannasolutions.co.zm.conf"
    "conf.d/enter.savannasolutions.co.zm.conf"
    "conf.d/onboard.savannasolutions.co.zm.conf"
    "community/odoo.conf"
    "enterprise/odoo.conf"
)

# Check each file in the list
echo "Checking for unnecessary .conf files in the stack..."
for conf_file in "${conf_files[@]}"; do
    check_conf_file "$conf_file"
done

# Optionally, list all .conf files in conf.d and other directories (for further manual inspection)
echo ""
echo "Listing all .conf files in conf.d and other directories for manual inspection..."
find . -type f -name "*.conf"
