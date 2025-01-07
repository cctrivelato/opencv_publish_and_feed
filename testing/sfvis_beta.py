import cv2
import socket
import jetson.inference
import jetson.utils
import mysql.connector
from mysql.connector import Error
from configparser import ConfigParser
import time
import getpass
import subprocess
from datetime import datetime, timedelta
import threading
from flask import Flask, Response

frame_rate = 40
app = Flask(__name__)
frame1 = None
frame2 = None
camera_group = {}
local = {}
hostname = socket.gethostname()

def read_db_config(filename='dbconfig.ini', section='database'):
    parser = ConfigParser()
    parser.read(filename)
    db = {}
    if parser.has_section(section):
        items = parser.items(section)
        for item in items:
            db[item[0]] = item[1]
    else:
        raise Exception(f'Section {section} not found in {filename}')
    return db

db_config = read_db_config()

class Camera:
    def __init__(self, station, sfvis, previous_status, time_spent, status, people_count, frame_rate, presence_total, presence_60, presence_rate, ret, frame, cap, time_started, first_time, pause, checkpoint, cuda_img, detections):
        self.station = station
        self.sfvis = sfvis
        self.previous_status = previous_status
        self.time_spent = time_spent
        self.status = status
        self.people_count = people_count
        self.frame_rate = frame_rate
        self.presence_total = presence_total
        self.presence_60 = presence_60
        self.presence_rate = presence_rate
        self.ret = ret
        self.frame = frame
        self.cap = cap
        self.time_started = time_started
        self.first_time = first_time
        self.pause = pause
        self.checkpoint = checkpoint
        self.cuda_img = cuda_img
        self.detections = detections
        self.jpeg = None

# Collects hostname and returns only its integer unique identification
def findSFVISno (hostname):
    import re
    number_of_sfvis = re.search(r'\d+', hostname)
    return number_of_sfvis.group() if number_of_sfvis else None

def devices(camera_devices):
    import re
    match = re.search(r'\d+', camera_devices)  # Search for the first sequence of digits
    return int(match.group()) if match else None

def get_camera_devices():
    result = subprocess.run(['v4l2-ctl', '--list-devices'], capture_output=True, text=True)
    devices = []
    if result.returncode == 0:
        lines = result.stdout.split('\n')
        for i in range(len(lines)):
            if '/dev/video' in lines[i]:
                devices.append(lines[i].strip())
    return devices

# Get camera devices
def place_cameras():
    camera_devices = get_camera_devices()
    camera_amount = int((len(camera_devices))/2)
    print(f"{int(len(camera_devices)/2)} cameras connected to: {len(camera_devices)} devices")
    position = {}
    counter = 0
    for i in range(len(camera_devices)):
        position[i] = devices(camera_devices[i])
        if position[i] % 2 == 0:
            local[counter] = position[i]
            counter = counter + 1
    return camera_amount

# Initialize the camera using OpenCV
def initialize_camera(camera_id):
    cap = cv2.VideoCapture(camera_id)  # Open cameras
    if not cap.isOpened():
        print(f"Error: Could not open the camera {camera_id}.")
        return None
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1080)  
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, frame_rate)  # Lower frame rate to reduce load
    
    return cap
    
# Initialize the Jetson Inference object detection model
def initialize_model():
    return jetson.inference.detectNet("ssd-mobilenet-v2", threshold=0.5)

# Function to count the number of people detected
def get_people_count(detections):
    people_count = sum(1 for detection in detections if detection.ClassID == 1 and detection.Confidence > 0.60)  # ClassID 1 is for 'person' and check if confidence level is bigger than 60%
    return people_count

# Function to generate frames for Camera 1
def generate_camera_1():
    while True:
        if frame1 is not None:
            ret, jpeg = cv2.imencode('.jpg', frame1)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

# Function to generate frames for Camera 2
def generate_camera_2():
    while True:
        if frame2 is not None:
            ret, jpeg = cv2.imencode('.jpg', frame2)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

# Flask route for Camera 1 feed
@app.route('/camera1')
def camera1_feed():
    return Response(generate_camera_1(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Flask route for Camera 2 feed
@app.route('/camera2')
def camera2_feed():
    return Response(generate_camera_2(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Method to get the workstation info
def get_workstation(sfvis, camera_place):
    if camera_place == 1:
        workstation = (int(sfvis)*2 - 1)
    elif camera_place == 2:
        workstation = (int(sfvis)*2) 
    return workstation
    

# Method to get the workstation status (occupied or unoccupied)
def get_workstation_status(people_count):
    if people_count != 0:
        status = "Occupied"
    else:
        status = "Vacant"
    return status

# Method to format time to HH:MM:SS format
def get_formatted_time(elapsed_seconds):
    elapsed_time = timedelta(seconds=elapsed_seconds)
    
    formatted_time = str(elapsed_time)
    
    if len(formatted_time.split(":")) == 2:
        formatted_time = "00:" + formatted_time
        
    return formatted_time

# Method to get the time one person spent working at welding booth
def get_working_time(start):
    end_time = time.time()
    elapsed_t = end_time - start
    time_spent = get_formatted_time(elapsed_t)
    
    return time_spent

def create_table(sfvis, station):    
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()

        # Create table for cam 1
        create_table_cam1_query = f"""
        CREATE TABLE IF NOT EXISTS `sfvis_cam{station}` (
            `Timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            `Workstation_Camera` INT NOT NULL,
            `Vision_System` INT NOT NULL,
            `Old_Status` VARCHAR(45) NOT NULL,
            `Period_Status_Last` TIME(6) DEFAULT NULL,
            `New_Status` VARCHAR(45) NOT NULL,
            `People_Count` INT NOT NULL,
            `Frame_Rate` INT NOT NULL,
            `Presence_Change_Total` INT NOT NULL,
            `Presence_Change_Rate` INT NOT NULL
        )
        """
        cursor.execute(create_table_cam1_query)
        print(f"Table `sfvis_cam{station}` is ready.")

        # Create table for sfvis
        create_table_sfvis_query = f"""
            CREATE TABLE IF NOT EXISTS `sfvis{sfvis}` (
                `Timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                `Workstation_Camera` INT NOT NULL,
                `Vision_System` INT NOT NULL,
                `Old_Status` VARCHAR(45) NOT NULL,
                `Period_Status_Last` TIME(6) DEFAULT NULL,
                `New_Status` VARCHAR(45) NOT NULL,
                `People_Count` INT NOT NULL,
                `Frame_Rate` INT NOT NULL,
                `Presence_Change_Total` INT NOT NULL,
                `Presence_Change_Rate` INT NOT NULL
            )
            """
        cursor.execute(create_table_sfvis_query)
        print(f"Table `sfvis{sfvis}` is ready.")

    except mysql.connector.Error as e:
        print(f"MySQL Error: {e}")

    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("MySQL connection is closed")

# Function to delete oldest item of the Grafana on the MySQL
def delete_function(cursor, connection, station):
    count_query = f"SELECT COUNT(*) FROM sfvis_cam{str(station)};"
    cursor.execute(count_query)
    row_count = cursor.fetchone()[0]

    try:
        if row_count > 10:
            delete_query = f"""
                DELETE FROM sfvis_cam{station}
                WHERE Timestamp = (
                    SELECT Timestamp
                    FROM (
                        SELECT Timestamp
                        FROM sfvis_cam{station}
                        ORDER BY Timestamp ASC
                        LIMIT 1
                    ) AS subquery
                );
                """
            print()
            cursor.execute(delete_query)  #multi=True here
            connection.commit()
            print(f"Oldest record deleted from sfvis_cam{station}.")
        
        else:
            print()
            print(f"Row count in sfvis_cam{station} is {row_count} and that's below the threshold. No deletion required.")

    except mysql.connector.Error as e:
        print(f"Error while deleting records from sfvis_cam{station}: {e}")
        connection.rollback()  # Rollback to maintain data integrity

# Function to publish count data to MySQL database (Non-blocking using threading)
def publish_to_mysql(people_count, station, time_spent, status, previous_status, sfvis, presence_rate, presence_total):
    def publish():
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()
            
            timestamp = datetime.now()

            if not sfvis.isalnum() or not str(station).isdigit():
                raise ValueError("Invalid table name or station number.")

            # Base SQL queries
            base_query = (
                "INSERT INTO {table} "
                "(Timestamp, WorkStation_Camera, Vision_System, Old_Status, {time_field}New_Status, People_Count, Frame_Rate, Presence_Change_Total, Presence_Change_Rate) "
                "VALUES (%s, %s, %s, %s, {time_placeholder}%s, %s, %s, %s, %s)"
            )

            # Adjust query for time_spent
            if time_spent:
                time_field = "Period_Status_Last, "
                time_placeholder = "%s, "
                data = (timestamp, station, sfvis, previous_status, time_spent, status, people_count, frame_rate, presence_total, presence_rate)
            else:
                time_field = ""
                time_placeholder = ""
                data = (timestamp, station, sfvis, previous_status, status, people_count, frame_rate, presence_total, presence_rate)

            # Final queries
            query_sfvis = base_query.format(table=f"sfvis{sfvis}", time_field=time_field, time_placeholder=time_placeholder)
            query_cam = base_query.format(table=f"sfvis_cam{station}", time_field=time_field, time_placeholder=time_placeholder)

            # Execute queries
            print()
            cursor.execute(query_sfvis, data)
            cursor.execute(query_cam, data)

            connection.commit()

            print(f"Published to MySQL: {people_count} people at Cam{station}")

            delete_function(cursor, connection, station)

        except Error as err:
            print(f"Database error: {err}")
        except ValueError as e:
            print(f"Validation error: {e}")

        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()

    # Run the publish function in a separate thread to avoid blocking
    threading.Thread(target=publish).start()

def check_status(camera):
    if camera.status != camera.previous_status: 
        if camera.status == "Occupied" and camera.previous_status == "Vacant":
            camera.time_started = time.time()
            publish_to_mysql(camera.people_count, camera.station, camera.time_spent, camera.status, camera.previous_status, camera.sfvis, camera.presence_rate, camera.presence_total)
            time.sleep(0.5)
            
            camera.previous_status = "Occupied"

        elif camera.status == "Vacant" and camera.previous_status == "Occupied":
            camera.presence_rate = 1 + camera.presence_rate

            camera.time_spent = get_working_time(camera.time_started)
            publish_to_mysql(camera.people_count, camera.station, camera.time_spent, camera.status, camera.previous_status, camera.sfvis, camera.presence_rate, camera.presence_total)
            time.sleep(0.5)
            
            camera.previous_status = "Vacant"
            camera.time_started = None
            camera.time_spent = None

def regular_post(camera, check_time):
    if (check_time % 60) == 0:
        camera.presence_total = camera.presence_total + camera.presence_rate
        camera.presence_60 = camera.presence_rate
        camera.presence_rate = 0

    publish_to_mysql(camera.people_count, camera.station, None, camera.status, camera.previous_status, camera.sfvis, camera.presence_60, camera.presence_total)
    camera.pause = True

def main():
    sfvis = findSFVISno(hostname)
    model = initialize_model()

    global frame1, frame2

    camera_amount = place_cameras()
    
    for i in range(camera_amount):
        print(f"Camera {i+1} is positioned in: /dev/video{local[i]}")

    try:
        for i in range(camera_amount):
            cap = initialize_camera(local[i])
            if cap is None:
                print(f"Skipping camera {i + 1} due to initialization error.")
                continue

            camera_group[i] = Camera(get_workstation(sfvis, i+1), sfvis, "Vacant", None, "Vacant", 0, frame_rate, 0, 0, 0, None, None, cap, None, True, False, None, None, None)
            create_table(sfvis, camera_group[i].station)

    except Error as err:
        print(f"Error in the user input: {err}")

    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)).start()

    overall_time = time.time()

    while True:
        for i in range(camera_amount):
            if i == 0:
                ret1, frame1 = camera_group[i].cap.read()
                if not ret1:
                    print("Error: Failed to read from the camera 1.")
                    break
            elif i == 1:
                ret2, frame2 = camera_group[i].cap.read()
                if not ret2:
                    print("Error: Failed to read from the camera 1.")
                    break
        
            camera_group[i].ret, camera_group[i].frame = camera_group[i].cap.read()
            if not camera_group[i].ret:
                print("Error: Failed to read from the camera 1.")
                break

            camera_group[i].cuda_img = jetson.utils.cudaFromNumpy(camera_group[i].frame)
            camera_group[i].detections = model.Detect(camera_group[i].cuda_img)
            camera_group[i].people_count = get_people_count(camera_group[i].detections)
            camera_group[i].status = get_workstation_status(camera_group[i].people_count)
            
            check_status(camera_group[i])

            camera_group[i].check_time = int(time.time() - overall_time)

            if not camera_group[i].pause:
                if (camera_group[i].check_time % 20) == 0:
                    camera_group[i].checkpoint = time.time()    
                    regular_post(camera_group[i], camera_group[i].check_time)

            if camera_group[i].checkpoint is not None: 
                testing = time.time() - camera_group[i].checkpoint
                if str(f"{testing:.1f}") >= "1.0":
                    camera_group[i].pause = False
                    camera_group[i].checkpoint = None

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    for i in range(camera_amount):
        camera_group[i].cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
