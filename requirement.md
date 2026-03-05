# Project Requirements: RobotJudge-CI

To run this project on a fresh Windows machine with "less work", ensures the following requirements are met.

## Software Requirements
- **Git**: [Download Git for Windows](https://git-scm.com/download/win). Required to clone the repository.
- **Docker Desktop**: [Download Docker Desktop](https://www.docker.com/products/docker-desktop/). **Highly Recommended**.
  - *Note*: Requires WSL2 (Windows Subsystem for Linux), which Docker will help you install.
- **Python 3.10+**: [Download Python](https://www.python.org/downloads/windows/) (if running natively without Docker).
- **Ngrok**: [Sign up for Ngrok](https://dashboard.ngrok.com/signup) to get an auth token if you want to expose the web interface publicly.

## Hardware Requirements
- **RAM**: Minimum 8GB (Docker Desktop requires a few GBs).
- **Storage**: ~500MB for the project and containers (initial).
- **Internet**: Required for initial dependency downloads.

## Connectivity
- **Port 8000**: Used by the web server.
- **Port 5432**: Used by the PostgreSQL database.
