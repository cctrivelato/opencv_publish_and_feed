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

    # Update package lists
    run_command("sudo apt install git cmake python3-pip")

    # Install MySQL Connector for Python
    run_command("pip3 install mysql-connector-python")

    # Install Flask
    run_command("pip3 install Flask")

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

    run_command("sudo apt update \
                sudo apt install -y \
                        build-essential \
                        cmake \
                        pkg-config \
                        libjpeg-dev \
                        libpng-dev \
                        libtiff-dev \
                        libdcmtk-dev \
                        gfortran \
                        python3-dev \
                        libeigen3-dev \
                        libblas-dev \
                        liblapack-dev \
                        libgtk2.0-dev \
                        libvtk6-dev \
                        libgstreamer1.0-dev \
                        libgstreamer-plugins-base1.0-dev \
                        gstreamer1.0-tools \
                        gstreamer1.0-plugins-good \
                        gstreamer1.0-plugins-bad \
                        gstreamer1.0-plugins-ugly \
                        gstreamer1.0-libav \
                        libcanberra-gtk-module \
                        libgdk-pixbuf2.0-dev")

    run_command("pip3 install opencv-python")

    run_command("pip3 install opencv-python-headless")

    run_command("sudo apt-get install libgtk2.0-dev")

    run_command("sudo apt-get install pkg-config")

    # Install additional Python libraries
    run_command("pip3 install numpy")

    print("All necessary packages installed.")

if __name__ == "__main__":
    install_packages()