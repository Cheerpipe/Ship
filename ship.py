#!/usr/bin/env python3
import os
import sys
import subprocess
import platform
import re
import fcntl
import json
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================================================================
# Script: ship (Docker Compose Updater)
# Version: 5.7.3 (Final) | Author: Felipe Urzúa & Gemini
# ==============================================================================

VERSION = "5.7.3"
AUTHOR = "Felipe Urzúa & Gemini"
SLOGAN = "Don't sink the ship :D"
LOCK_FILE = "/tmp/ship.pid"
LOG_FILE = os.path.expanduser("~/.ship_errors.log")

# Network and concurrency configuration
SCAN_DELAY_MS = 200  
last_request_time = 0
rate_lock = threading.Lock()   # Protects access to the Docker Hub API
map_lock = threading.Lock()    # Protects the futures dictionary in multi-threaded context

# UI Colors and formatting
RED, GREEN, YELLOW, CYAN = "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[0;36m"
GRAY, BOLD, NC, CLEAR_LINE = "\033[1;30m", "\033[1m", "\033[0m", "\033[K"

def get_timestamp():
    """Generates a formatted timestamp for logging purposes."""
    return f"{GRAY}[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{NC}"

def display_header():
    """Prints the script header to the terminal."""
    print(f"{CYAN}{BOLD}ship v{VERSION}{NC} | {GRAY}Author: {AUTHOR}{NC}")
    print(f"{YELLOW}{BOLD}{SLOGAN}{NC}")

def run_cmd(cmd):
    """Executes a system command and returns its output (stdout, stderr)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return "", str(e)

def get_arch():
    """Detects system architecture to filter images on Docker Hub."""
    m = platform.machine().lower()
    if m in ["x86_64", "amd64"]: return "amd64"
    if m in ["aarch64", "arm64", "armv8"]: return "arm64"
    return m

def get_remote_digest(image, arch, verbose, delay_ms):
    """
    Retrieves the SHA256 Digest of an image from the remote registry.
    Implements a global delay (delay_ms) to prevent Rate Limit blocks.
    """
    global last_request_time
    with rate_lock:
        current_time = time.time() * 1000
        elapsed = current_time - last_request_time
        if elapsed < delay_ms:
            time.sleep((delay_ms - elapsed) / 1000.0)
        last_request_time = time.time() * 1000

    stdout, stderr = run_cmd(f"docker buildx imagetools inspect {image}")
    if any(err in stderr for err in ["429 Too Many Requests", "toomanyrequests"]):
        return "RATE_LIMIT_ERROR"
    if not stdout: return None
    
    pattern = rf"sha256:[a-f0-9]{{64}}.*?Platform:.*?linux/{arch}"
    match = re.search(pattern, stdout, re.DOTALL)
    if match: return re.search(r"sha256:[a-f0-9]{64}", match.group()).group()
    
    global_match = re.search(r"^Digest:\s+(sha256:[a-f0-9]{64})", stdout, re.MULTILINE)
    return global_match.group(1) if global_match else None

def check_stack(directory, verbose, delay_ms, force=False):
    """
    Analyzes a directory to determine if its Docker services require an update.
    Compares remote vs local Digest, and local Image ID vs running Image ID.
    If force=True, marks the stack for update immediately, bypassing checks.
    """
    yaml_files = ["docker-compose.yml", "docker-compose.yaml"]
    yaml_path = next((os.path.join(directory, f) for f in yaml_files if os.path.exists(os.path.join(directory, f))), None)
    if not yaml_path: return "NO_COMPOSE", ""

    if force:
        return "UPDATE", f"\n    {YELLOW}├─ MODE: FORCE ENABLED{NC}\n    {YELLOW}└─ STATUS: UPDATE TRIGGERED BY USER{NC}"

    abs_path = os.path.abspath(directory)
    compose_ps, _ = run_cmd(f"docker compose -f {yaml_path} ps --format json")
    ps_data = []
    try:
        ps_data = json.loads(compose_ps)
        if isinstance(ps_data, dict): ps_data = [ps_data]
    except: pass

    config_json, _ = run_cmd(f"docker compose -f {yaml_path} config --format json")
    needs_update, rate_limited, log_acc = False, False, ""
    arch = get_arch()

    try:
        services = json.loads(config_json).get('services', {})
    except:
        imgs, _ = run_cmd(f"docker compose -f {yaml_path} config --images")
        services = {f"svc_{i}": {"image": img} for i, img in enumerate(imgs.splitlines()) if img}

    for svc_name, svc_info in services.items():
        img = svc_info.get('image')
        if not img: continue
        
        local_inspect, _ = run_cmd(f"docker image inspect {img} --format '{{{{json .RepoDigests}}}}|{{{{.Id}}}}'")
        local_dig = next(iter(re.findall(r"sha256:[a-f0-9]{64}", local_inspect.split('|')[0])), None)
        local_id = local_inspect.split('|')[1] if '|' in local_inspect else "N/A"
        
        container_id = next((c.get('ID') or c.get('Id') for c in ps_data if c.get('Service') == svc_name), None)
        if container_id:
            running_img_id, _ = run_cmd(f"docker inspect --format '{{{{.Image}}}}' {container_id}")
        else:
            project_name = os.path.basename(abs_path).lower().replace("_", "").replace("-", "")
            running_img_id, _ = run_cmd(f"docker inspect --format '{{{{.Image}}}}' {project_name}-{svc_name}-1 2>/dev/null || docker inspect --format '{{{{.Image}}}}' {svc_name} 2>/dev/null")
        
        if not running_img_id: running_img_id = "NOT_FOUND"
        remote_hash = get_remote_digest(img, arch, verbose, delay_ms)
        
        if remote_hash == "RATE_LIMIT_ERROR":
            rate_limited = True
            continue

        svc_needs_pull = remote_hash and local_dig and remote_hash != local_dig
        svc_needs_recreate = local_id != "N/A" and running_img_id != "NOT_FOUND" and local_id != running_img_id

        if verbose:
            log_acc += f"\n    {BOLD}Service:{NC} {svc_name}"
            log_acc += f"\n    {GRAY}├─ Image:    {NC}{img}"
            log_acc += f"\n    {GRAY}├─ Remote D: {NC}{YELLOW}{remote_hash or 'N/A'}{NC}"
            log_acc += f"\n    {GRAY}├─ Local D:  {NC}{CYAN}{local_dig or 'N/A'}{NC}"
            log_acc += f"\n    {GRAY}├─ Local ID: {NC}{GRAY}{local_id[:15]}...{NC}"
            log_acc += f"\n    {GRAY}└─ Run ID:   {NC}{GRAY}{running_img_id[:15]}...{NC}"
            
            if svc_needs_pull: log_acc += f"\n    {RED}└─ STATUS: PULL REQUIRED{NC}"
            elif svc_needs_recreate: log_acc += f"\n    {YELLOW}└─ STATUS: RECREATE REQUIRED (ID MISMATCH){NC}"
            else: log_acc += f"\n    {GREEN}└─ STATUS: UP TO DATE{NC}"

        if svc_needs_pull or svc_needs_recreate:
            needs_update = True
            
    if rate_limited: return "RATE_LIMIT", log_acc
    return ("UPDATE" if needs_update else "OK"), log_acc

def install_ship():
    """Installs the script into /usr/local/bin for global execution."""
    if os.geteuid() != 0:
        print(f"{RED}Error: Run with sudo.{NC}"); sys.exit(1)
    dest = "/usr/local/bin/ship"
    if os.path.exists(dest):
        with open(dest, 'r') as f:
            v_match = re.search(r'VERSION = "([^"]+)"', f.read())
            print(f"{YELLOW}Existing: v{v_match.group(1) if v_match else 'Old'} | New: v{VERSION}{NC}")
        if input("Overwrite? [y/N] ").lower() != 'y': sys.exit(0)
    import shutil
    shutil.copyfile(__file__, dest)
    os.chmod(dest, 0o755)
    print(f"{GREEN}Success: ship v{VERSION} installed.{NC}"); sys.exit(0)

def spawn_tasks(executor, targets, futures_map, verbose, delay, force):
    """Background thread that spawns scan tasks with a staggered launch (delay)."""
    for target in targets:
        with map_lock:
            future = executor.submit(check_stack, target, verbose, delay, force)
            futures_map[future] = target
        time.sleep(delay / 1000.0)

def main():
    """Main entry point: Handles arguments, scanning orchestration, and deployment."""
    import argparse
    parser = argparse.ArgumentParser(
        description=f"ship v{VERSION} - Docker Compose Updater",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False
    )
    
    # Standard Options
    group = parser.add_argument_group(f"{CYAN}{BOLD}Available Parameters{NC}")
    group.add_argument("-a", "--all", action="store_true", help="Scan all subdirectories for valid compose files.")
    group.add_argument("-f", "--force", action="store_true", help="Bypass hash comparison and force update on targets.")
    group.add_argument("-y", "--yes", action="store_true", help="Bypass user confirmation before processing.")
    group.add_argument("-p", "--prune", action="store_true", help="Execute 'docker image prune -f' after updates.")
    group.add_argument("-v", "--verbose", action="store_true", help="Enable detailed technical report of hashes and IDs.")
    group.add_argument("-j", "--jobs", type=int, default=100, help="Max concurrent worker threads (Default: 100).")
    group.add_argument("-d", "--delay", type=int, default=SCAN_DELAY_MS, help="Interval between thread launches in ms (Default: 200).")
    group.add_argument("-h", "--help", action="help", help="Show this help message and exit.")
    group.add_argument("--install", action="store_true", help="Deploy the script to /usr/local/bin/ship.")
    parser.add_argument("targets", nargs="*", help="Specific directories to scan.")

    args = parser.parse_args()

    if args.install: install_ship()
    display_header()
    
    valid_targets, updatable = [], []
    if args.all:
        for d in sorted(next(os.walk('.'))[1]):
            if os.path.exists(".dcuignore"):
                with open(".dcuignore", 'r') as f:
                    if d in f.read().splitlines(): continue
            valid_targets.append(d)
    else:
        for t in [t.rstrip('/') for t in args.targets]:
            if os.path.isdir(t): valid_targets.append(t)

    if not valid_targets:
        print(f"{YELLOW}No targets found. Use -a to scan all or specify a directory.{NC}")
        sys.exit(0)

    print(f"{BOLD}Scanning {len(valid_targets)} stacks...{NC}")

    futures_map = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        spawner = threading.Thread(target=spawn_tasks, args=(executor, valid_targets, futures_map, args.verbose, args.delay, args.force))
        spawner.daemon = True
        spawner.start()

        count = 0
        while count < len(valid_targets):
            with map_lock:
                current_futures = list(futures_map.keys())
            
            if not current_futures:
                time.sleep(0.1)
                continue

            for future in as_completed(current_futures):
                with map_lock:
                    if future in futures_map:
                        count += 1
                        target = futures_map.pop(future)
                        status, logs = future.result()
                        print(f"\r{CLEAR_LINE}{GRAY}[{count}/{len(valid_targets)}]{NC} Checked: {BOLD}{target}{NC}", end="", flush=True)
                        if status == "UPDATE": updatable.append(target)
                        if args.verbose: print(f"\n{CYAN}Analysis:{NC} {BOLD}{target}{NC}{logs}\n")
            time.sleep(0.05)
    
    print(f"\r{CLEAR_LINE}", end="")

    if not updatable:
        print(f"\n{GREEN}{BOLD}Everything is at the latest version.{NC}"); sys.exit(0)

    status_label = "Ready to update (Force Mode):" if args.force else "Updates available for:"
    print(f"\n{CYAN}{BOLD}{status_label}{NC} {BOLD}{' '.join(updatable)}{NC}")
    
    if not args.yes and input(f"\nProceed with update? [Y/n] ").lower() not in ['', 'y']: sys.exit(0)

    f_lock = open(LOCK_FILE, 'w')
    try:
        fcntl.lockf(f_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for target in updatable:
            name = os.path.basename(target)
            print(f"{get_timestamp()} {CYAN}{BOLD}➜ STACK:{NC} {BOLD}{name}{NC}")
            yaml = next((os.path.join(target, f) for f in ["docker-compose.yml", "docker-compose.yaml"] if os.path.exists(os.path.join(target, f))), None)
            with open(LOG_FILE, "a") as log:
                print(f"   {NC}├─ [INFO] Pulling...", end="", flush=True)
                subprocess.run(f"docker compose -f {yaml} pull", shell=True, stderr=log, stdout=log)
                print(" Done.")
                print(f"   {GREEN}├─ [NEW] Recreating (Force)...{NC}")
                u = subprocess.run(f"docker compose -f {yaml} up -d --force-recreate", shell=True, stderr=log, stdout=log)
                print(f"   {GREEN if u.returncode == 0 else RED}└─ [{'SUCCESS' if u.returncode == 0 else 'FAILED'}].{NC}")
            print(f"   {GRAY}{'─'*54}{NC}")
        if args.prune: run_cmd("docker image prune -f")
    except IOError: print(f"{RED}Error: Already running.{NC}")
    finally:
        f_lock.close()
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)

if __name__ == "__main__": main()
