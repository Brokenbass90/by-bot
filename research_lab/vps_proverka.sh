#!/bin/bash
# vps_proverka.sh — прежнее имя. Проверка переехала в vps_zdorovye.sh.
exec bash "$(dirname "$0")/vps_zdorovye.sh" "$@"
