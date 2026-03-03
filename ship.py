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
import shlex
import logging
from enum import Enum
from contextlib import contextmanager
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==============================================================================
# Script: ship (Docker Compose Updater)
# Version: 5.7.9 (Cleanup Feedback) | Author: Felipe Urzúa & Gemini
# ==============================================================================

VERSION = "5.7.9"
AUTHOR = "Felipe Urzúa & Gemini"
SLOGAN = "Don't sink the ship :D"
LOCK_FILE = "/tmp/ship.pid"

SCAN_DELAY_MS = 200
DOCKER_BUILDX_TIMEOUT = 60
DOCKER_CMD_TIMEOUT = 60

# ANSI Color codes
RED, GREEN, YELLOW, CYAN = "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[0;36m"
GRAY, BOLD, NC, CLEAR_LINE = "\033[1;30m", "\033[1m", "\033[0m", "\033[K"

# Compiled regex patterns for efficiency
SHA256_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
FULL_SHA_WITH_PLATFORM_PATTERN = re.compile(rf"sha256:[a-f0-9]{{64}}.*?Platform:.*?linux/(?P<arch>\w+)", re.DOTALL)
DIGEST_PATTERN = re.compile(r"^Digest:\s+(sha256:[a-f0-9]{64})", re.MULTILINE)
VERSION_PATTERN = re.compile(r'VERSION = "([^"]+)"')

class ScanStatus(Enum):
    """Enumeration for scan status results."""
    UPDATE = "UPDATE"
    OK = "OK"
    NO_COMPOSE = "NO_COMPOSE"
    RATE_LIMIT = "RATE_LIMIT"

class Config:
    """Configuration holder for script execution."""
    def __init__(self):
        self.log_path = os.path.expanduser("~/.ship_errors.log")
        self.verbose = False
        self.delay_ms = SCAN_DELAY_MS
        self.force = False
        self.yes = False
        self.prune = False
        self.jobs = 100
        self.last_request_time = 0
        self.rate_lock = threading.Lock()
        self.map_lock = threading.Lock()
    
    def set_log_path(self, path):
        """Set custom log path."""
        if path:
            self.log_path = path
    
    def setup_logging(self):
        """Configure logging for the application."""
        logger = logging.getLogger('ship')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(self.log_path)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler (for errors)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.ERROR)
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

# Global logger instance
logger = None

def get_timestamp():
    """Generates a formatted timestamp for logging purposes."""
    return f"{GRAY}[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]{NC}"

def display_header():
    """Prints the script header to the terminal."""
    print(f"{CYAN}{BOLD}ship v{VERSION}{NC} | {GRAY}Author: {AUTHOR}{NC}")
    print(f"{YELLOW}{BOLD}{SLOGAN}{NC}")

def run_cmd(cmd, timeout=DOCKER_CMD_TIMEOUT):
    """
    Executes a system command and returns its output.
    
    Args:
        cmd: Command string to execute
        timeout: Timeout in seconds
        
    Returns:
        Tuple of (stdout, stderr, success_flag)
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode == 0
    except subprocess.TimeoutExpired:
        error_msg = f"Command timeout after {timeout}s: {cmd}"
        logger.error(error_msg) if logger else None
        return "", error_msg, False
    except FileNotFoundError as e:
        logger.error(f"Command not found: {e}") if logger else None
        return "", str(e), False
    except Exception as e:
        logger.error(f"Command execution failed: {e}") if logger else None
        return "", str(e), False

def check_docker_installed():
    """Validates that Docker is installed and accessible."""
    _, _, success = run_cmd("docker --version", timeout=10)
    if not success:
        print(f"{RED}Error: Docker is not installed or not in PATH.{NC}")
        sys.exit(1)

@contextmanager
def acquire_lock(lock_file_path, timeout=10):
    """
    Context manager for acquiring file lock.
    
    Args:
        lock_file_path: Path to lock file
        timeout: Timeout in seconds
        
    Yields:
        File object if lock acquired
        
    Raises:
        IOError: If lock cannot be acquired
    """
    f_lock = None
    try:
        f_lock = open(lock_file_path, 'w')
        fcntl.lockf(f_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield f_lock
    except IOError as e:
        logger.error(f"Failed to acquire lock: {e}") if logger else None
        raise IOError(f"Ship is already running (lock file: {lock_file_path})")
    finally:
        if f_lock:
            try:
                fcntl.lockf(f_lock, fcntl.LOCK_UN)
                f_lock.close()
            except Exception as e:
                logger.error(f"Error releasing lock: {e}") if logger else None
        try:
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
        except Exception as e:
            logger.error(f"Error removing lock file: {e}") if logger else None

def get_arch():
    """Detects system architecture."""
    m = platform.machine().lower()
    if m in ["x86_64", "amd64"]: return "amd64"
    if m in ["aarch64", "arm64", "armv8"]: return "arm64"
    return m

def get_remote_digest(image, arch, config):
    """
    Retrieves the SHA256 Digest from remote registry with rate limiting.
    
    Args:
        image: Image name/tag
        arch: Architecture (amd64, arm64, etc)
        config: Config instance with rate limiting settings
        
    Returns:
        SHA256 digest string, or None if not found, or "RATE_LIMIT_ERROR"
    """
    with config.rate_lock:
        current_time = time.time() * 1000
        elapsed = current_time - config.last_request_time
        if elapsed < config.delay_ms:
            time.sleep((config.delay_ms - elapsed) / 1000.0)
        config.last_request_time = time.time() * 1000
    
    # Safely quote the image name
    safe_image = shlex.quote(image)
    stdout, stderr, success = run_cmd(f"docker buildx imagetools inspect {safe_image}", timeout=DOCKER_BUILDX_TIMEOUT)
    
    if not success:
        if any(err in stderr for err in ["429 Too Many Requests", "toomanyrequests"]):
            return "RATE_LIMIT_ERROR"
        logger.debug(f"Failed to inspect image {image}: {stderr}") if logger else None
        return None
    
    if not stdout:
        return None
    
    # Try to find digest with platform-specific match
    match = FULL_SHA_WITH_PLATFORM_PATTERN.search(stdout)
    if match:
        digest_match = SHA256_PATTERN.search(match.group())
        if digest_match:
            return digest_match.group()
    
    # Fallback to global digest
    digest_match = DIGEST_PATTERN.search(stdout)
    return digest_match.group(1) if digest_match else None

def check_stack(directory, config):
    """
    Analyzes a directory to determine if updates are needed.
    
    Args:
        directory: Directory path to scan
        config: Config instance
        
    Returns:
        Tuple of (ScanStatus, logs_string)
    """
    yaml_files = ["docker-compose.yml", "docker-compose.yaml"]
    yaml_path = next(
        (os.path.join(directory, f) for f in yaml_files if os.path.exists(os.path.join(directory, f))),
        None
    )
    
    if not yaml_path:
        return ScanStatus.NO_COMPOSE, ""
    
    if config.force:
        log_msg = f"\n    {YELLOW}├─ MODE: FORCE ENABLED{NC}\n    {YELLOW}└─ STATUS: UPDATE TRIGGERED BY USER{NC}"
        return ScanStatus.UPDATE, log_msg
    
    abs_path = os.path.abspath(directory)
    
    # Get running containers
    safe_yaml = shlex.quote(yaml_path)
    compose_ps, _, _ = run_cmd(f"docker compose -f {safe_yaml} ps --format json")
    ps_data = []
    try:
        ps_data = json.loads(compose_ps)
        if isinstance(ps_data, dict):
            ps_data = [ps_data]
    except json.JSONDecodeError as e:
        logger.debug(f"Failed to parse compose ps for {directory}: {e}") if logger else None
    
    # Get service configuration
    config_json, _, _ = run_cmd(f"docker compose -f {safe_yaml} config --format json")
    needs_update, rate_limited, log_acc = False, False, ""
    arch = get_arch()
    
    try:
        services = json.loads(config_json).get('services', {})
    except json.JSONDecodeError:
        logger.debug(f"Failed to parse docker-compose config, falling back to image list") if logger else None
        imgs, _, _ = run_cmd(f"docker compose -f {safe_yaml} config --images")
        services = {f"svc_{i}": {"image": img} for i, img in enumerate(imgs.splitlines()) if img}
    
    for svc_name, svc_info in services.items():
        img = svc_info.get('image')
        if not img:
            continue
        
        safe_img = shlex.quote(img)
        
        # Get local image info
        local_inspect, _, _ = run_cmd(f"docker image inspect {safe_img} --format '{{{{json .RepoDigests}}}}|{{{{.Id}}}}'")
        local_dig = next(iter(SHA256_PATTERN.findall(local_inspect.split('|')[0])), None) if '|' in local_inspect else None
        local_id = local_inspect.split('|')[1] if '|' in local_inspect else "N/A"
        
        # Get running container ID
        container_id = next((c.get('ID') or c.get('Id') for c in ps_data if c.get('Service') == svc_name), None)
        
        if container_id:
            running_img_id, _, _ = run_cmd(f"docker inspect --format '{{{{.Image}}}}' {shlex.quote(container_id)}")
        else:
            project_name = os.path.basename(abs_path).lower().replace("_", "").replace("-", "")
            cmd = f"docker inspect --format '{{{{.Image}}}}' {shlex.quote(f'{project_name}-{svc_name}-1')} 2>/dev/null || docker inspect --format '{{{{.Image}}}}' {shlex.quote(svc_name)} 2>/dev/null"
            running_img_id, _, _ = run_cmd(cmd)
        
        if not running_img_id:
            running_img_id = "NOT_FOUND"
        
        # Get remote digest
        remote_hash = get_remote_digest(img, arch, config)
        if remote_hash == "RATE_LIMIT_ERROR":
            rate_limited = True
            continue
        
        # Determine if update needed
        svc_needs_pull = remote_hash and local_dig and remote_hash != local_dig
        svc_needs_recreate = local_id != "N/A" and running_img_id != "NOT_FOUND" and local_id != running_img_id
        
        if config.verbose:
            log_acc += f"\n    {BOLD}Service:{NC} {svc_name}"
            log_acc += f"\n    {GRAY}├─ Image:    {NC}{img}"
            log_acc += f"\n    {GRAY}├─ Remote D: {NC}{YELLOW}{remote_hash or 'N/A'}{NC}"
            log_acc += f"\n    {GRAY}├─ Local D:  {NC}{CYAN}{local_dig or 'N/A'}{NC}"
            log_acc += f"\n    {GRAY}├─ Local ID: {NC}{GRAY}{local_id[:15]}...{NC}"
            log_acc += f"\n    {GRAY}└─ Run ID:   {NC}{GRAY}{running_img_id[:15]}...{NC}"
            
            if svc_needs_pull:
                log_acc += f"\n    {RED}└─ STATUS: PULL REQUIRED{NC}"
            elif svc_needs_recreate:
                log_acc += f"\n    {YELLOW}└─ STATUS: RECREATE REQUIRED (ID MISMATCH){NC}"
            else:
                log_acc += f"\n    {GREEN}└─ STATUS: UP TO DATE{NC}"
        
        if svc_needs_pull or svc_needs_recreate:
            needs_update = True
    
    if rate_limited:
        return ScanStatus.RATE_LIMIT, log_acc
    
    return (ScanStatus.UPDATE if needs_update else ScanStatus.OK), log_acc

def install_ship():
    """Universal Installer for ship."""
    if os.geteuid() != 0:
        print(f"{RED}Error: Run with sudo.{NC}")
        sys.exit(1)
    
    dest = "/usr/local/bin/ship"
    
    if os.path.exists(dest):
        try:
            with open(dest, 'r') as f:
                content = f.read()
                v_match = VERSION_PATTERN.search(content)
                v_old = v_match.group(1) if v_match else 'Unknown'
                print(f"{YELLOW}Existing: v{v_old} | New: v{VERSION}{NC}")
        except IOError as e:
            logger.error(f"Failed to read existing installation: {e}") if logger else None
            print(f"{YELLOW}Could not read existing version{NC}")
        
        if input("Overwrite? [y/N] ").lower() != 'y':
            sys.exit(0)
    
    try:
        source_url = "https://raw.githubusercontent.com/Cheerpipe/Ship/refs/heads/main/ship.py"
        source_code = None
        
        # Try to read from local file first
        if "__file__" in globals() and "__file__" not in [None, '']:
            try:
                with open(__file__, 'r') as f:
                    source_code = f.read()
            except (IOError, FileNotFoundError):
                pass
        
        # Fallback to downloading from GitHub
        if source_code is None:
            try:
                import urllib.request
                with urllib.request.urlopen(source_url, timeout=10) as response:
                    source_code = response.read().decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to download from GitHub: {e}") if logger else None
                raise
        
        # Write to destination
        with open(dest, 'w') as f:
            f.write(source_code)
        
        os.chmod(dest, 0o755)
        print(f"{GREEN}Success: ship v{VERSION} installed globally.{NC}")
        
    except (IOError, OSError) as e:
        logger.error(f"Installation failed: {e}") if logger else None
        print(f"{RED}Installation failed: {str(e)}{NC}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during installation: {e}") if logger else None
        print(f"{RED}Unexpected error: {str(e)}{NC}")
        sys.exit(1)
    
    sys.exit(0)

def spawn_tasks(executor, targets, futures_map, config):
    """
    Spawns scan tasks with a staggered launch.
    
    Args:
        executor: ThreadPoolExecutor instance
        targets: List of directories to scan
        futures_map: Dictionary mapping futures to targets
        config: Config instance
    """
    for target in targets:
        with config.map_lock:
            future = executor.submit(check_stack, target, config)
            futures_map[future] = target
        time.sleep(config.delay_ms / 1000.0)

def main():
    """Main entry point."""
    global logger
    import argparse
    
    description = f"""ship v{VERSION} - Docker Compose Container Updater

A simple and easy-to-use application designed to automatically update Docker containers
created with docker-compose. It scans your docker-compose configurations, detects when
container images have updates available, and seamlessly pulls and recreates containers
with the latest versions."""
    
    parser = argparse.ArgumentParser(
        description=description,
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_argument_group(f"{CYAN}{BOLD}Available Parameters{NC}")
    group.add_argument(
        "-a", "--all",
        action="store_true",
        help="Scan all directories in the current location for docker-compose files and update them (default: disabled)"
    )
    group.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force container recreation even if images are already up-to-date (default: disabled)"
    )
    group.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip user confirmation and proceed directly with the update process (default: disabled, prompts user)"
    )
    group.add_argument(
        "-p", "--prune", "--purge",
        action="store_true",
        help="Remove unused Docker images after updating containers to reclaim disk space (default: disabled)"
    )
    group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Display detailed information about each scanned service and update process (default: disabled)"
    )
    group.add_argument(
        "-j", "--jobs",
        type=int,
        default=100,
        help="Number of concurrent scanning tasks to run in parallel (default: 100)"
    )
    group.add_argument(
        "-d", "--delay",
        type=int,
        default=SCAN_DELAY_MS,
        help="Delay in milliseconds between registry requests to avoid rate limiting (default: 200ms)"
    )
    group.add_argument(
        "--log-path",
        type=str,
        default=None,
        help=f"Path where error logs will be saved (default: {os.path.expanduser('~/.ship_errors.log')})"
    )
    group.add_argument(
        "-h", "--help",
        action="help",
        help="Show this help message and exit"
    )
    group.add_argument(
        "--install",
        action="store_true",
        help="Install ship globally to /usr/local/bin/ship (requires sudo)"
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="Directory paths containing docker-compose files to update (leave empty with -a to scan all directories)"
    )

    args = parser.parse_args()
    
    # Initialize config
    config = Config()
    config.verbose = args.verbose
    config.delay_ms = args.delay
    config.force = args.force
    config.yes = args.yes
    config.prune = args.prune
    config.jobs = args.jobs
    config.set_log_path(args.log_path)
    
    # Setup logger
    logger = config.setup_logging()
    
    # Handle install mode
    if args.install:
        install_ship()
        return
    
    display_header()
    
    # Validate Docker installation
    check_docker_installed()
    
    # Check if no arguments were provided
    if not args.all and not args.targets:
        print(f"\n{YELLOW}No parameters provided.{NC}")
        print(f"Use {BOLD}-h{NC} or {BOLD}--help{NC} to see available options.\n")
        parser.print_help()
        sys.exit(0)
    
    # Collect target directories
    valid_targets = []
    if args.all:
        for d in sorted(next(os.walk('.'))[1]):
            if os.path.exists(".dcuignore"):
                try:
                    with open(".dcuignore", 'r') as f:
                        if d in f.read().splitlines():
                            continue
                except IOError as e:
                    logger.warning(f"Failed to read .dcuignore: {e}")
            valid_targets.append(d)
    else:
        for t in [t.rstrip('/') for t in args.targets]:
            if os.path.isdir(t):
                valid_targets.append(t)
            else:
                logger.warning(f"Target is not a directory: {t}")

    if not valid_targets:
        print(f"{YELLOW}No valid targets found.{NC}")
        sys.exit(0)

    # Scan directories
    print(f"{BOLD}Scanning directories...{NC}")
    futures_map = {}
    updatable = []
    
    try:
        with ThreadPoolExecutor(max_workers=config.jobs) as executor:
            # Start spawning tasks
            spawner = threading.Thread(
                target=spawn_tasks,
                args=(executor, valid_targets, futures_map, config),
                daemon=True
            )
            spawner.start()
            
            # Process results as they complete
            count = 0
            while count < len(valid_targets):
                with config.map_lock:
                    current_futures = list(futures_map.keys())
                
                if not current_futures:
                    time.sleep(0.1)
                    continue
                
                for future in as_completed(current_futures):
                    with config.map_lock:
                        if future not in futures_map:
                            continue
                        
                        count += 1
                        target = futures_map.pop(future)
                        
                        try:
                            status, logs = future.result()
                            print(
                                f"\r{CLEAR_LINE}{GRAY}[{count}/{len(valid_targets)}]{NC} Checked: {BOLD}{target}{NC}",
                                end="",
                                flush=True
                            )
                            
                            if status == ScanStatus.UPDATE:
                                updatable.append(target)
                            
                            if config.verbose and logs:
                                print(f"\n{CYAN}Analysis:{NC} {BOLD}{target}{NC}{logs}\n")
                        except Exception as e:
                            logger.error(f"Error processing {target}: {e}")
                            print(f"\n{RED}Error scanning {target}: {e}{NC}")
                
                time.sleep(0.05)
    
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Scan interrupted by user.{NC}")
        logger.info("Scan interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error during scanning: {e}")
        print(f"\n{RED}Error during scanning: {e}{NC}")
        sys.exit(1)
    
    # Display results
    print(f"\r{CLEAR_LINE}", end="")
    if not updatable:
        print(f"\n{GREEN}{BOLD}Everything is at the latest version.{NC}")
        sys.exit(0)

    # Show stacks to update
    status_label = "Ready to update (Force Mode):" if config.force else "Stacks identified for update:"
    print(f"\n{CYAN}{BOLD}{status_label}{NC}")
    print(f"{CYAN}{' '.join(updatable)}{NC}")
    print(f"\n{BOLD}Summary: Total of {len(updatable)} stack(s) to process.{NC}")

    # Confirm before updating
    if not config.yes:
        user_input = input(f"\nProceed with update process? [Y/n] ")
        if user_input.lower() not in ['', 'y']:
            logger.info("Update cancelled by user")
            sys.exit(0)

    # Execute updates with proper locking
    try:
        with acquire_lock(LOCK_FILE) as f_lock:
            for i, target in enumerate(updatable, 1):
                name = os.path.basename(target)
                print(f"{get_timestamp()} [{i}/{len(updatable)}] {CYAN}➜ PROCESSING STACK:{NC} {BOLD}{name}{NC}")
                
                yaml = next(
                    (os.path.join(target, f) for f in ["docker-compose.yml", "docker-compose.yaml"]
                     if os.path.exists(os.path.join(target, f))),
                    None
                )
                
                if not yaml:
                    logger.error(f"No docker-compose file found in {target}")
                    print(f"   {RED}└─ ERROR: No docker-compose file found{NC}")
                    continue
                
                safe_yaml = shlex.quote(yaml)
                
                try:
                    with open(config.log_path, "a") as log:
                        # Pull images
                        print(f"   {NC}├─ [INFO] Pulling remote images... ", end="", flush=True)
                        pull_cmd = f"docker compose -f {safe_yaml} pull"
                        _, _, pull_success = run_cmd(pull_cmd)
                        
                        if not pull_success:
                            logger.warning(f"docker compose pull failed for {target}")
                            print(f"{RED}Failed{NC}.")
                            continue
                        
                        print("Done.")
                        
                        # Recreate containers
                        recreate_flag = "--force-recreate" if config.force else ""
                        mode_text = "Force" if config.force else "Standard"
                        print(f"   {GREEN}└─ [NEW] Recreating ({mode_text})...{NC}", end="", flush=True)
                        
                        up_cmd = f"docker compose -f {safe_yaml} up -d {recreate_flag}".strip()
                        _, _, up_success = run_cmd(up_cmd)
                        
                        status_text = f" {GREEN if up_success else RED}[{'SUCCESS' if up_success else 'FAILED'}].{NC}"
                        print(status_text)
                        
                        if up_success:
                            logger.info(f"Successfully updated stack: {name}")
                        else:
                            logger.error(f"Failed to update stack: {name}")
                
                except IOError as e:
                    logger.error(f"Failed to write to log file: {e}")
                    print(f"   {RED}└─ ERROR: Could not write logs{NC}")
                
                print(f"   {GRAY}{'─'*54}{NC}")
            
            # Cleanup phase
            if config.prune:
                print(f"\n{get_timestamp()} {YELLOW}➜ SYSTEM CLEANUP: Pruning unused Docker images...{NC}", end="", flush=True)
                _, _, prune_success = run_cmd("docker image prune -f")
                if prune_success:
                    print(f" {GREEN}[SUCCESS]{NC}")
                    logger.info("Docker image prune completed successfully")
                else:
                    print(f" {RED}[FAILED]{NC}")
                    logger.warning("Docker image prune encountered errors")
        
        print(f"\n{GREEN}{BOLD}Update process completed.{NC}")
        logger.info("Update process completed successfully")
    
    except IOError as e:
        print(f"{RED}Error: {str(e)}{NC}")
        logger.error(f"Lock error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Update process interrupted by user.{NC}")
        logger.info("Update process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error during update: {e}")
        print(f"\n{RED}Unexpected error: {e}{NC}")
        sys.exit(1)

if __name__ == "__main__":
    main()
