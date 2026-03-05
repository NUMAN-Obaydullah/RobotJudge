# Windows Setup Guide - RobotJudge-CI

Follow these steps to get the project running on a fresh Windows PC.

## Option 1: Using Docker (easiest & Recommended)

### 1-A. Install Docker Desktop
1.  **Download**: Get the installer from [docker.com](https://www.docker.com/products/docker-desktop/).
2.  **Install**: Run the installer. Ensure **"Use WSL 2 instead of Hyper-V"** is checked (it usually is by default).
3.  **WSL2 Update**: if prompted, follow the link to install the [WSL2 Linux Kernel Update](https://learn.microsoft.com/en-us/windows/wsl/install).
4.  **Restart**: You will likely need to restart your PC after installation.
5.  **Start Docker**: Open Docker Desktop and wait for the "Engine" to start (green icon at bottom left).

### 1-B. Project Setup
1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/NUMAN-Obaydullah/RobotJudge.git
    cd RobotJudge
    ```
2.  **Setup Environment Variables**:
    - Copy `.env.example` to `.env`.
    - Edit `.env` and add your `NGROK_AUTHTOKEN` (optional).
3.  **Run with Docker Compose**:
    ```bash
    docker-compose up --build
    ```
4.  **Access the App**: Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Option 2: Native Manual Setup (Less Recommended)

1.  **Install Python 3.10+**: Ensure "Add Python to PATH" is checked during installation.
2.  **Install Git**: From [git-scm.com](https://git-scm.com/).
3.  **Run Automation Script**:
    Double-click `setup.bat` or run it in CMD/PowerShell:
    ```cmd
    .\setup.bat
    ```
4.  **Run the Server**:
    ```cmd
    .venv\Scripts\activate
    python web/server.py
    ```

> [!IMPORTANT]
> This project requires a PostgreSQL database. If you use the native setup, you must install and configure PostgreSQL manually. Using Docker (Option 1) handles this automatically for you.
