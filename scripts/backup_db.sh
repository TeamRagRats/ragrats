#!/bin/bash
BACKUP_DIR="/home/golddigger/Desktop/back up databaser"
FILENAME="ragrats_backup_$(date +%Y%m%d_%H%M%S).sql"

docker exec ragrats_database pg_dump -U teamragrats ragrats > "$BACKUP_DIR/$FILENAME"
