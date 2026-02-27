# 🚢 ship (Docker Compose Updater)

> **"A streamlined automation tool for Docker stack maintenance."**

**ship** is a lightweight Bash utility designed to automate the 'pull-and-recreate' cycle of Docker Compose stacks by detecting image changes via hash comparison.

## 🌟 Introduction

I developed **ship** to simplify the maintenance of containers in my local home automation environment. It is primarily intended for **homelabs** and users who want to efficiently update multiple containers across different directories without manual intervention.

**⚠️ Disclaimer:** This tool is built for convenience. While it facilitates rapid updates, users should remain cautious. Controlling container versions and reviewing changelogs is a fundamental practice for stable environments. Use **ship** responsibly.

---

## ⚡ Quick Install (One-Liner)

You can install **ship** instantly without manual downloads by running this command (requires `curl`):

```bash
sudo bash -c "$(curl -sSL https://raw.githubusercontent.com/Cheerpipe/Ship/main/ship.sh)" -- --install
```

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
* **Hash Comparison:** Recreates containers only if a new image hash is detected on the registry.
* **Exclusion Support:** Skip specific directories using a `.dcuignore` file.
* **Professional Output:** Clean, technical terminal UI with precise status reporting.
* **Pre-flight Validation:** Checks for Docker socket permissions and dependencies before execution.

---

## 🚫 Excluding Directories (.dcuignore)

If you use the `-a` or `--all` flag, you can prevent **ship** from touching specific directories by creating a file named `.dcuignore` in the root folder where you run the script.

**Example `.dcuignore` content:**
```text
database_prod
legacy_app_do_not_touch
testing_environment
```
*The script will completely skip these folders during the scanning process.*

---

## 📋 Dependencies

| Requirement | Purpose | Documentation |
| :--- | :--- | :--- |
| **Docker Engine** | Core container runtime | [Official Docs](https://docs.docker.com/engine/install/) |
| **Docker Compose V2** | CLI plugin for stack management | [Official Docs](https://docs.docker.com/compose/install/) |
| **GNU Coreutils** | UI formatting via `fmt` | [GNU Project](https://www.gnu.org/software/coreutils/) |

---

## 📖 How to Use

### Syntax
`ship [options] [target_directories]`

### Available Parameters

| Parameter | Alias | Technical Description |
| :--- | :--- | :--- |
| `--all` | `-a` | Automatically scans all subdirectories for valid compose files. |
| `--yes` | `-y` | Force mode: bypasses user confirmation before processing updates. |
| `--prune` | `-p` | Executes `docker image prune -f` after the update cycle. |
| `--verbose` | `-v` | Enables detailed stdout for technical debugging. |
| `--help` | `-h` | Displays the help menu and version information. |
| `--install` | | Deploys the script to `/usr/local/bin/ship`. |

---

## 🪵 Error Logging

In case of execution failure, the script generates a technical log at:
`~/.ship_errors.log`

---
*Developed by Felipe Urzúa in collaboration with Gemini AI.*
