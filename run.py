import os
import subprocess


def run_api_server():
    try:
        subprocess.run(["python", "backend/api_server.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running api_server.py: {e}")

if __name__ == "__main__":
    run_api_server()
