# Windows Setup Guide - RobotJudge-CI

Follow these steps to get the project running on a fresh Windows PC.

## Option 1: Using Docker (easiest & Recommended)

1.  **Install Docker Desktop**: Download and install from [docker.com](https://www.docker.com/products/docker-desktop/).
2.  **Clone the Repository**:
    ```bash
    git clone https://github.com/NUMAN-Obaydullah/RobotJudge.git
    cd RobotJudge
    ```
3.  **Setup Environment Variables**:
    - Copy `.env.example` to `.env`.
    - Edit `.env` and add your `NGROK_AUTHTOKEN` (optional, for public access).
4.  **Run with Docker Compose**:
    ```bash
    docker-compose up --build
    ```
5.  **Access the App**: Open [http://localhost:8000](http://localhost:8000) in your browser.

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
