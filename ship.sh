#!/bin/bash

# ==============================================================================
# 🚢 ship - Docker Compose Stack Updater
# Version: 3.9.2
# Developed by: Felipe Urzúa & Gemini AI
# License: Creative Commons Attribution-NonCommercial 4.0 International
# ==============================================================================

# --- Configuration & Colors ---
VERSION="v3.9.2"
REPO_URL="https://raw.githubusercontent.com/Cheerpipe/Ship/main/ship.sh"
ERROR_LOG="$HOME/.ship_errors.log"
PID_FILE="/tmp/.ship.pid"

# Colors
BLUE='\033[0;34m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Core Functions ---

log_error() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >> "$ERROR_LOG"
}

check_seaworthiness() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}ERROR:${NC} Docker is not installed."
        exit 1
    fi
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}ERROR:${NC} Docker Compose V2 is required."
        exit 1
    fi
    if ! docker ps &> /dev/null; then
        echo -e "${RED}ERROR:${NC} Cannot connect to Docker socket."
        exit 1
    fi
}

show_help() {
    echo -e "${BLUE}ship${NC} - The streamlined Docker Compose updater ${CYAN}$VERSION${NC}"
    echo ""
    echo -e "${YELLOW}USAGE:${NC}"
    echo "  ship [options] [target_directories]"
    echo ""
    echo -e "${YELLOW}OPTIONS:${NC}"
    echo "  -a, --all       Scan all subdirectories for docker-compose files"
    echo "  -y, --yes       Auto-confirm all updates/installation"
    echo "  -p, --prune     Remove unused images after update"
    echo "  -v, --verbose   Show detailed technical output"
    echo "  -h, --help      Show this help menu"
    echo "      --install   Install ship globally to /usr/local/bin"
    echo ""
}

# --- Installation Logic (Refined v3.9.2) ---

install_ship() {
    local bin_dest="/usr/local/bin/ship"
    local auto_confirm=$1

    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}ERROR:${NC} Administrative privileges required!"
        echo "Try: curl -sSL $REPO_URL | sudo bash -s -- --install"
        exit 1
    fi

    echo -e "${BLUE}Preparing installation of ship $VERSION...${NC}"

    if [[ -f "$bin_dest" ]]; then
        local current_v=$($bin_dest --version 2>/dev/null || echo "unknown")
        echo -e "${YELLOW}Existing installation detected (Version: $current_v).${NC}"
        if [[ "$auto_confirm" != true ]]; then
            read -p "Overwrite and update to $VERSION? [y/N] " confirm
            [[ "$confirm" != "y" && "$confirm" != "Y" ]] && { echo "Installation cancelled."; exit 0; }
        fi
    else
        if [[ "$auto_confirm" != true ]]; then
            read -p "Do you want to install ship $VERSION in $bin_dest? [y/N] " confirm
            [[ "$confirm" != "y" && "$confirm" != "Y" ]] && { echo "Installation cancelled."; exit 0; }
        fi
    fi

    # Logic to handle installation from file or from curl pipe
    if [[ -f "$0" && "$0" != "/bin/bash" && "$0" != "bash" ]]; then
        cp "$0" "$bin_dest"
    else
        echo -e "${CYAN}Downloading source from repository...${NC}"
        if ! curl -sSL "$REPO_URL" -o "$bin_dest"; then
            echo -e "${RED}ERROR:${NC} Failed to download from $REPO_URL"
            exit 1
        fi
    fi

    chmod +x "$bin_dest"
    echo -e "${GREEN}Success:${NC} ship $VERSION installed at $bin_dest"
    exit 0
}

# --- Update Engine ---

process_stack() {
    local dir=$1
    local auto_yes=$2
    local verbose=$3

    (
        cd "$dir" || return
        local compose_file=""
        [[ -f "docker-compose.yml" ]] && compose_file="docker-compose.yml"
        [[ -f "docker-compose.yaml" ]] && compose_file="docker-compose.yaml"

        if [[ -z "$compose_file" ]]; then
            [[ "$verbose" == true ]] && echo -e "${YELLOW}Skipping $dir:${NC} No compose file found."
            return
        fi

        echo -e "${BLUE}Checking stack:${NC} $dir"
        local old_hashes=$(docker compose images -q)
        
        if [[ "$verbose" == true ]]; then
            docker compose pull
        else
            docker compose pull &> /dev/null
        fi

        local new_hashes=$(docker compose images -q)

        if [[ "$old_hashes" != "$new_hashes" ]]; then
            echo -e "${CYAN}Update available!${NC} Changes detected."
            local confirm
            if [[ "$auto_yes" != true ]]; then
                read -p "Apply update to $dir? [y/N] " confirm
            fi
            if [[ "$auto_yes" == true || "$confirm" == "y" || "$confirm" == "Y" ]]; then
                docker compose up -d --remove-orphans
                echo -e "${GREEN}Stack updated.${NC}"
            else
                echo "Update skipped."
            fi
        else
            echo "No changes detected."
        fi
        echo "---"
    )
}

# --- Main Execution ---

# Detect flags before anything else
AUTO_YES=false
for arg in "$@"; do
    [[ "$arg" == "-y" || "$arg" == "--yes" ]] && AUTO_YES=true
done

if [[ "$1" == "--version" ]]; then
    echo "$VERSION"
    exit 0
fi

if [[ "$1" == "--install" || "$2" == "--install" ]]; then
    install_ship "$AUTO_YES"
    exit 0
fi

check_seaworthiness

# PID lock
if [[ -f "$PID_FILE" ]]; then
    pid=$(cat "$PID_FILE")
    if ps -p "$pid" > /dev/null; then
        echo -e "${RED}ERROR:${NC} ship is already running."
        exit 1
    fi
fi
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE" &>/dev/null' EXIT

ALL_FLAG=false
PRUNE_FLAG=false
VERBOSE=false
TARGET_DIRS=()

while [[ "$#" -gt 0 ]]; do
    case $1 in
        -a|--all) ALL_FLAG=true ;;
        -y|--yes) AUTO_YES=true ;;
        -p|--prune) PRUNE_FLAG=true ;;
        -v|--verbose) VERBOSE=true ;;
        -h|--help) show_help; exit 0 ;;
        *) TARGET_DIRS+=("$1") ;;
    esac
    shift
done

if [[ "$ALL_FLAG" == true ]]; then
    IGNORE_LIST=(".git" "node_modules")
    if [[ -f ".dcuignore" ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" || "$line" =~ ^# ]] && continue
            IGNORE_LIST+=("${line// /}")
        done < ".dcuignore"
    fi

    for d in */; do
        dir_name=${d%/}
        skip=false
        for ignore in "${IGNORE_LIST[@]}"; do
            [[ "$dir_name" == "$ignore" ]] && skip=true && break
        done
        [[ "$skip" == true ]] && continue
        process_stack "$dir_name" "$AUTO_YES" "$VERBOSE"
    done
elif [[ ${#TARGET_DIRS[@]} -gt 0 ]]; then
    for dir in "${TARGET_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            process_stack "$dir" "$AUTO_YES" "$VERBOSE"
        else
            echo -e "${RED}Error:${NC} Directory '$dir' not found."
        fi
    done
else
    show_help
fi

if [[ "$PRUNE_FLAG" == true ]]; then
    echo -e "${YELLOW}Pruning unused images...${NC}"
    docker image prune -f
fi

echo -e "${GREEN}Finished.${NC}"
