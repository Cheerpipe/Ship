 # 🚢 ship (Docker Compose Updater)
 
 > **"A streamlined automation tool for Docker stack maintenance."**
 
 **ship** is a lightweight Bash utility designed to automate the 'pull-and-recreate' cycle of Docker Compose stacks by detecting image changes via hash comparison.
 
 ## 🌟 Introduction
 
 I developed **ship** to simplify the maintenance of containers in my local home automation environment. It is primarily intended for **homelabs** and users who want to efficiently update multiple containers across different directories without manual intervention.
 
 **⚠️ Disclaimer:** This tool is built for convenience. While it facilitates rapid updates, users should remain cautious. Controlling container versions and reviewing changelogs is a fundamental practice for stable environments. Use **ship** responsibly.
 
 ---
 
 ## 🤖 The Build Process: A Human-AI Collaboration
 
 This script is the result of an **iterative evolutionary process** between myself and **Gemini (Google's AI)**. 
 
 ### Development Journey:
 * **Iterative Engineering:** We started with a basic update logic and evolved into a robust solution featuring hash-based change detection, safety locks, and professional error handling.
 * **Code Inspection:** I utilized the AI to perform intensive code audits, identifying edge cases, permission bottlenecks, and dependency requirements.
 * **Human Oversight:** During development, I performed real-time testing to detect regressions (such as logic gaps or inconsistent language). The AI acted as a technical partner, refactoring and repairing the code based on my feedback until reaching the stable v3.8.
 * **AI Optimization:** The AI suggested implementing the `check_seaworthiness` function for pre-execution validation and the `.ship.pid` mechanism to prevent concurrent execution conflicts.
 
 ---
 
 ## 🛠 Features
 
 * **Recursive Processing:** Update all stacks within subdirectories in a single pass.
 * **Hash Comparison:** Recreates containers only if a new image hash is detected on the registry, saving time and resources.
 * **Professional Output:** Clean, technical terminal UI with precise status reporting.
 * **Pre-flight Validation:** Rigorous checks for Docker socket permissions and system dependencies before execution.
 * **Automated Cleanup:** Optional image pruning to maintain system storage health.
 
 ---
 
 ## 📋 Dependencies
 
 The script validates the following dependencies before execution:
 
 | Requirement | Purpose | Documentation |
 | :--- | :--- | :--- |
 | **Docker Engine** | Core container runtime | [Official Docs](https://docs.docker.com/engine/install/) |
 | **Docker Compose V2** | CLI plugin for stack management | [Official Docs](https://docs.docker.com/compose/install/) |
 | **GNU Coreutils** | UI formatting via `fmt` | [GNU Project](https://www.gnu.org/software/coreutils/) |
 
 ---
 
 ## 🚀 Installation
 
 To install **ship** globally:
 
 1. Download the `ship.sh` source file.
 2. Grant execution permissions:
    ```bash
    chmod +x ship.sh
    ```
 3. Execute the internal installer with administrative privileges:
    ```bash
    sudo ./ship.sh --install
    ```
 4. Access the tool globally using the `ship` command.
 
 ---
 
 ## 📖 How to Use
 
 ### Syntax
 `ship [options] [target_directories]`
 
 ### Available Parameters
 
 | Parameter | Alias | Technical Description |
 | :--- | :--- | :--- |
 | `--all` | `-a` | Automatically scans all subdirectories for valid compose files. |
 | `--yes` | `-y` | Force mode: bypasses user confirmation before processing updates. |
 | `--prune` | `-p` | Executes `docker image prune` after the update cycle is complete. |
 | `--verbose` | `-v` | Enables detailed stdout for technical debugging. |
 | `--help` | `-h` | Displays the help menu and version information. |
 | `--install` | | Deploys the script to `/usr/local/bin/ship`. |
 
 ### Usage Examples
 
 * **Update specific stacks:**
     ```bash
     ship stack_folder_01 stack_folder_02
     ```
 * **Full automated update with cleanup:**
     ```bash
     ship -a -y -p
     ```
 
 ---
 
 ## 🪵 Error Logging
 
 In case of execution failure, the script generates a technical log at:
 `~/.ship_errors.log`
 
 ---
 *Developed by Felipe Urzúa in collaboration with Gemini AI.*
