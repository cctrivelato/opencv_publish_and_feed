import subprocess
import sys
import os

def run_command(command):
    """Run a system command and check for errors."""
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

def install_packages():
    # Ensure python3 is available as python
    run_command("sudo update-alternatives --install /usr/bin/python python /usr/bin/python3 1")

    # Update package lists
    run_command("sudo apt update")

    # Install required system packages
    run_command("sudo apt-get install -y v4l-utils python3-pip")

    # Install Python libraries
    run_command("pip3 install mysql-connector-python Flask opencv-python numpy")

    # Get the current directory where the script is located
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the new directory for jetson_inference
    jetson_inference_dir = os.path.join(current_dir, "jetson_inference")

    # Create the new directory if it does not exist
    if not os.path.exists(jetson_inference_dir):
        print(f"Creating directory {jetson_inference_dir}")
        os.makedirs(jetson_inference_dir)

        # Clone the Jetson Inference repository into the new directory
        os.chdir(jetson_inference_dir)
        run_command("git clone --recursive https://github.com/dusty-nv/jetson-inference")

        # Install Jetson Inference (assumes you have the necessary environment)
        os.chdir(os.path.join(jetson_inference_dir, "jetson-inference"))
        run_command("git submodule update --init")
        run_command("mkdir build")
        os.chdir("build")
        run_command("cmake ../")
        run_command("make")
        run_command("sudo make install")
        run_command("sudo ldconfig")

    print("All necessary packages installed.")

def find_file(filename, search_path):
    """Search for a file recursively within a directory."""
    for root, dirs, files in os.walk(search_path):
        if filename in files:
            return os.path.join(root, filename)
    return None

def setup_systemd_service(service_name, script_path):
    """Set up the systemd service for the CV script."""
    service_file = f"/etc/systemd/system/{service_name}.service"
    service_content = f"""
[Unit]
Description=Computer Vision Script Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 {script_path}
Restart=always
User={os.getenv("USER")}
WorkingDirectory={os.path.dirname(script_path)}

[Install]
WantedBy=multi-user.target
    """

    # Write the service file
    with open(f"{service_name}.service", "w") as f:
        f.write(service_content)

    # Move the service file to the system directory
    run_command(f"sudo mv {service_name}.service {service_file}")
    run_command("sudo systemctl daemon-reload")
    run_command(f"sudo systemctl enable {service_name}.service")
    run_command(f"sudo systemctl start {service_name}.service")

    print(f"Service {service_name} has been set up and started.")

if __name__ == "__main__":
    install_packages()

    target_file = "sfvis_beta.py"  # Replace with your CV script filename
    search_directory = os.getcwd()  # Start searching in the current directory

    # Find the file
    script_path = find_file(target_file, search_directory)

    if not script_path:
        print(f"Error: {target_file} not found in {search_directory}. Please check the filename and directory.")
        sys.exit(1)

    print(f"Found script at: {script_path}")

    # Service name
    service_name = "sfvis"

    setup_systemd_service(service_name, script_path)