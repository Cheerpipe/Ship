#!/bin/bash

# ==============================================================================
# Script: ship (Docker Compose Updater)
# Version: 3.8 (Professional) | Author: Felipe Urzúa & Gemini
# ==============================================================================

VERSION="3.8"
AUTHOR="Felipe Urzúa & Gemini"
SLOGAN="Don't sink the ship :D"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[1;30m'
NC='\033[0m'
BOLD='\033[1m'

LOCK_FILE="/tmp/ship.pid"
LOG_FILE="$HOME/.ship_errors.log"

# --- Core Utility Functions ---

get_timestamp() { echo -e "${GRAY}$(date +"[%Y-%m-%d %H:%M:%S]")${NC}"; }

# Mantiene el lenguaje náutico solo aquí
display_header() {
    echo -e "${CYAN}${BOLD}ship v$VERSION${NC} | ${GRAY}Author: $AUTHOR${NC}"
    echo -e "${YELLOW}${BOLD}$SLOGAN${NC}"
}

check_seaworthiness() {
    local missing=()
    local fail=false
    command -v docker >/dev/null 2>&1 || { missing+=("docker (Engine)"); fail=true; }
    command -v fmt >/dev/null 2>&1 || { missing+=("fmt (coreutils)"); fail=true; }
    if ! docker compose version >/dev/null 2>&1; then
        missing+=("docker-compose-plugin (V2)"); fail=true
    fi
    if [ "$fail" = true ]; then
        echo -e "${RED}${BOLD}ERROR: System requirements not met!${NC}"
        echo -e "Missing dependencies:"
        for item in "${missing[@]}"; do echo -e "  ${RED}[X]${NC} $item"; done
        exit 99
    fi
    if ! docker ps >/dev/null 2>&1; then
        echo -e "${RED}${BOLD}ERROR: Docker socket access denied!${NC}"
        echo -e "Check permissions. Recommendation: ${CYAN}sudo usermod -aG docker \$USER${NC}"
        exit 99
    fi
}

display_help() {
    display_header
    echo -e "\n${BOLD}DESCRIPTION:${NC}"
    echo -e "  ship automates the 'pull-and-recreate' cycle of your Docker stacks."
    echo -e "  Built for those who live for the thrill of a blind update."

    echo -e "\n${BOLD}USAGE:${NC} ship [options] [stack_dir1 stack_dir2 ...]"
    echo -e "\n${BOLD}OPTIONS:${NC}"
    echo -e "  ${YELLOW}-a, --all${NC}             Scan all subdirectories for compose files."
    echo -e "  ${YELLOW}-y, --yes${NC}             Skip confirmation and proceed with updates."
    echo -e "  ${YELLOW}-p, --prune${NC}           Remove unused images after execution."
    echo -e "  ${YELLOW}-v, --verbose${NC}         Display detailed execution logs."
    echo -e "  ${YELLOW}--install${NC}             Install 'ship' to /usr/local/bin."
    exit 0
}

install_ship() {
    local bin_dest="/usr/local/bin/ship"
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${RED}${BOLD}ERROR: Administrative privileges required!${NC}"
        echo -e "Command: ${CYAN}sudo ./ship.sh --install${NC}"
        exit 1 
    fi

    if [ -f "$bin_dest" ]; then
        local current_ver=$(grep -oP '^VERSION="\K[^"]+' "$bin_dest" 2>/dev/null || echo "Unknown")
        echo -e "${YELLOW}${BOLD}Existing installation detected:${NC}"
        echo -e "  Current version: v$current_ver"
        echo -e "  New version:     v$VERSION"
        echo -ne "\nOverwrite existing binary? [y/N] "
        read confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            echo -e "${GRAY}Installation cancelled by user.${NC}"
            exit 0
        fi
    fi

    cp "$0" "$bin_dest" && chmod +x "$bin_dest"
    echo -e "${GREEN}${BOLD}Success: ship v$VERSION installed at $bin_dest${NC}"
    exit 0
}

process_update() {
    local dir="$1"; local idx="$2"; local total="$3"
    local name=$(basename "$(cd "$dir" && pwd)")
    local yaml=""; [[ -f "$dir/docker-compose.yml" ]] && yaml="$dir/docker-compose.yml" || yaml="$dir/docker-compose.yaml"

    echo -e "$(get_timestamp) ${GRAY}[$idx/$total]${NC} ${CYAN}${BOLD}➜ PROCESSING STACK:${NC} ${BOLD}$name${NC}"
    
    local status=$(docker compose -f "$yaml" ps --format "{{.Status}}" 2>/dev/null)
    local active=false; [[ "$status" == *"running"* ]] && active=true

    echo -ne "$(get_timestamp)   ${NC}├─ [INFO] Pulling remote images..."
    docker compose -f "$yaml" pull >/dev/null 2>&1
    echo -e " Done."

    local ids=$(docker compose -f "$yaml" ps -q 2>/dev/null)
    local h_run=$( [ -z "$ids" ] && echo "OFF" || docker inspect --format '{{.Image}}' $ids 2>/dev/null | sort | xargs | tr -d ' ' )
    local imgs=$(docker compose -f "$yaml" config --images 2>/dev/null)
    local h_reg=""; for i in $imgs; do h=$(docker image inspect --format '{{.Id}}' "$i" 2>/dev/null); h_reg+="$h "; done
    h_reg=$(echo "$h_reg" | tr ' ' '\n' | sort | xargs | tr -d ' ')

    if [[ "$h_run" != "$h_reg" ]]; then
        if [ "$active" = false ]; then
            echo -e "$(get_timestamp)   ${YELLOW}└─ [SKIP] New images available, but stack is currently stopped.${NC}"
            SUMMARY_SKIPPED+=("$name")
        else
            echo -e "$(get_timestamp)   ${GREEN}├─ [NEW] Recreating containers with updated images...${NC}"
            if docker compose -f "$yaml" up -d >/dev/null 2>&1; then
                echo -e "$(get_timestamp)   ${GREEN}└─ [SUCCESS] Stack updated and running.${NC}"
                SUMMARY_SUCCESS+=("$name")
            else
                echo -e "$(get_timestamp)   ${RED}└─ [FAILED] Execution error. Check logs at $LOG_FILE${NC}"
                SUMMARY_ERROR+=("$name")
            fi
        fi
    else
        echo -e "$(get_timestamp)   ${YELLOW}└─ [OK] Stack is up to date.${NC}"
        SUMMARY_SKIPPED+=("$name")
    fi
    echo -e "   ${GRAY}──────────────────────────────────────────────────────${NC}"
}

# --- Runtime Logic ---

ALL_MODES=false; PRUNE=false; FORCE_YES=false; TARGET_DIRS=(); VALID_TARGETS=(); NOT_FOUND=(); NO_COMPOSE=();
declare -a SUMMARY_SUCCESS; declare -a SUMMARY_SKIPPED; declare -a SUMMARY_ERROR;

while [[ $# -gt 0 ]]; do
    case $1 in
        --install)    install_ship ;;
        -y|--yes)     FORCE_YES=true; shift ;;
        -a|--all)     ALL_MODES=true; shift ;;
        -p|--prune)   PRUNE=true; shift ;;
        -h|--help)    display_help ;;
        *)            TARGET_DIRS+=("$1"); shift ;;
    esac
done

check_seaworthiness

[[ "$ALL_MODES" = false && ${#TARGET_DIRS[@]} -eq 0 ]] && display_help

if [ "$ALL_MODES" = true ]; then
    for d in */; do
        d=${d%/}
        [[ -f ".dcuignore" ]] && grep -Fxq "$d" ".dcuignore" && continue
        [[ -f "$d/docker-compose.yml" || -f "$d/docker-compose.yaml" ]] && VALID_TARGETS+=("$d")
    done
else
    for t in "${TARGET_DIRS[@]}"; do
        if [ ! -d "$t" ]; then NOT_FOUND+=("$t")
        elif [[ ! -f "$t/docker-compose.yml" && ! -f "$t/docker-compose.yaml" ]]; then NO_COMPOSE+=("$t")
        else VALID_TARGETS+=("$t"); fi
    done
fi

display_header
echo -e "${BOLD}Scanning directories...${NC}"

if [ ${#NOT_FOUND[@]} -gt 0 ]; then
    echo -e "\n${RED}${BOLD}Directories not found:${NC}"
    echo "${NOT_FOUND[@]}" | fmt -w 80 | sed 's/^/  /'
fi

if [ ${#NO_COMPOSE[@]} -gt 0 ]; then
    echo -e "\n${YELLOW}${BOLD}Directories without compose files:${NC}"
    echo "${NO_COMPOSE[@]}" | fmt -w 80 | sed 's/^/  /'
fi

if [ ${#VALID_TARGETS[@]} -gt 0 ]; then
    echo -e "\n${BOLD}Stacks identified for update:${NC}"
    printf "${CYAN}%s${NC} " "${VALID_TARGETS[@]}" | fmt -w 80 | sed 's/^/  /'
    
    echo -e "\n\n${BOLD}Summary:${NC} Total of ${#VALID_TARGETS[@]} stack(s) to process."
    
    if [ "$FORCE_YES" = false ]; then
        echo -ne "\n${BOLD}Proceed with update process? [Y/n] ${NC}"
        read confirm
        [[ ! "$confirm" =~ ^[Yy]?$ ]] && { echo "Process aborted by user."; exit 0; }
    fi
else
    echo -e "\n${RED}ERROR: No valid stacks found to process.${NC}"; exit 100
fi

if [ -f "$LOCK_FILE" ]; then
    if kill -0 $(cat "$LOCK_FILE") 2>/dev/null; then
        echo -e "${RED}ERROR: Process lock detected. ship is already running.${NC}"; exit 1
    fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"; exit' INT TERM EXIT

echo -e "\n${CYAN}${BOLD}Executing ship v$VERSION...${NC}"
I=1
for dir in "${VALID_TARGETS[@]}"; do
    process_update "$dir" "$I" "${#VALID_TARGETS[@]}"
    ((I++))
done

if [ "$PRUNE" = true ]; then
    echo -e "\n$(get_timestamp) ${YELLOW}Cleaning up unused Docker images (prune)...${NC}"
    docker image prune -f >/dev/null
fi

echo -e "\n${CYAN}${BOLD}Execution Finished | Updated: ${#SUMMARY_SUCCESS[@]} | Up to date: ${#SUMMARY_SKIPPED[@]} | Failed: ${#SUMMARY_ERROR[@]}${NC}"
