 # 🚢 ship (Docker Compose Updater)

 > "A streamlined automation tool for Docker stack maintenance, now powered by Python."

 ship is a lightweight Python utility designed to automate the 'pull-and-recreate' cycle of Docker Compose stacks by detecting image changes via deep hash comparison.

 ## 🌟 Introduction

 I developed ship to simplify the maintenance of containers in my local home automation environment. The tool has evolved from a simple Bash script to a high-performance Python application capable of scanning dozens of stacks in seconds using asynchronous multithreading.

 ⚠️ Disclaimer: This tool is built for convenience. While it facilitates rapid updates, users should remain cautious. Controlling container versions and reviewing changelogs is a fundamental practice for stable environments. Use ship responsibly.

 ---

 ## ⚡ Quick Install (One-Liner)

 You can install ship instantly without manual downloads by running this command (requires curl and python3):

 ```bash
 sudo python3 -c "$(curl -sSL https://raw.githubusercontent.com/Cheerpipe/Ship/refs/heads/main/ship.py)" --install
 ```

 ---

 ## 🤖 The Build Process: A Human-AI Collaboration

 This script is the result of an iterative evolutionary process between myself and Gemini (Google's AI).

 ### Development Journey:
 * Version 5.0+ Shift: Migrated from Bash to Python to leverage true multithreading and better JSON parsing of Docker outputs.
 * Background Spawner Architecture: Implemented a non-blocking "spawner" thread that launches scan tasks every 200ms, ensuring a smooth UI and preventing API rate-limiting.
 * Deep Inspection: Evolved logic to compare not just Image Tags, but Remote Digests vs Local Digests and Local IDs vs Running Container IDs.
 * Zero Dependencies: Optimized to run using only the Python Standard Library, ensuring maximum portability across any Linux distribution.

 ---

 ## 🛠 Features

 * Multithreaded Scanning: Processes multiple stacks concurrently for extreme speed.
 * Staggered Launch: Prevents "429 Too Many Requests" errors from Docker Hub by spacing out registry queries.
 * Force Mode: Option to bypass hash checks and trigger immediate updates.
 * Triple-Check Validation: Recreates containers only if there's a real difference between the registry, the local cache, or the running container.
 * Zero External Dependencies: No pip install required. Pure Python 3.
 * Exclusion Support: Skip specific directories using a .dcuignore file.

 ---

 ## 🚫 Excluding Directories (.dcuignore)

 If you use the -a or --all flag, you can prevent ship from touching specific directories by creating a file named .dcuignore in the root folder where you run the script.

 Example .dcuignore content:
 text  database_prod  legacy_app_do_not_touch  testing_environment  

 ---

 ## 📋 Requirements

 | Requirement | Minimum Version | Recommended |
 | :--- | :--- | :--- |
 | Python 3 | 3.6+ (f-strings support) | 3.10+ |
 | Docker Engine | 20.10+ | Latest |
 | Docker Compose | V2 (Plugin) | Latest |
 | OS | Linux / WSL2 | Any Linux with Fcntl support |

 ---

 ## 📖 How to Use

 ### Syntax
 ship [options] [target_directories]

 ### Available Parameters

 | Parameter | Alias | Technical Description |
 | :--- | :--- | :--- |
 | --all | -a | Automatically scans all subdirectories for valid compose files. |
 | --force | -f | Bypasses hash comparison and forces pull & recreate on all targets. |
 | --yes | -y | Bypasses user confirmation before processing updates. |
 | --prune | -p | Executes docker image prune -f after the update cycle. |
 | --verbose | -v | Enables detailed technical report of every hash and ID compared. |
 | --jobs | -j [N] | Sets the maximum number of concurrent worker threads (Default: 100). |
 | --delay | -d [ms] | Sets the interval between thread launches in milliseconds (Default: 200). |
 | --install | | Deploys the script to /usr/local/bin/ship. |

 ---

 ## 🪵 Error Logging

 In case of execution failure, the script generates a technical log at:
 ~/.ship_errors.log

 ---
 Developed by Felipe Urzúa in collaboration with Gemini AI (v5.7.2).
