import cv2
import socket
import jetson.inference
import jetson.utils
import mysql.connector
from mysql.connector import Error
import time
import getpass
from datetime import datetime, timedelta
import threading
from flask import Flask, Response

frame_rate = 40
app = Flask(__name__)
frame = []

# Get machine's hostname
hostname = socket.gethostname()

username = None
pwd = None
host = None
database = None

# Collect DB details from User
def db_details():
    print("Insert here your Database Info ->")
    host = input("Host: ")
    database = input("Database: ")
    username = input("Username: ")
    pwd = getpass.getpass("Password: ")

    db = {
            'user': username,
            'password': pwd,
            'host': host,
            'database': database
        }
    
    return db

db_config = db_details()

class Camera:
    def __init__(self, station, sfvis, previous_status, time_spent, status, people_count, frame_rate, presence_total, presence_60, presence_rate, ret, frame, cap, time_started, first_time, pause, checkpoint, cuda_img, detections):
        self.worstation_camera = station
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

# Collects hostname and returns only its integer unique identification
def findSFVISno (hostname):
    import re
    number_of_sfvis = re.search(r'\d+', hostname)
    return number_of_sfvis.group() if number_of_sfvis else None

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

# Function to generate frames for Camera 2
def generate_camera(frame):
    while True:
        if frame is not None:
            ret, jpeg = cv2.imencode('.jpg', frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

# Flask route for Camera 1 feed
@app.route('/camera1')
def camera1_feed():
    return Response(generate_camera(frame[0]),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Flask route for Camera 2 feed
@app.route('/camera2')
def camera2_feed():
    return Response(generate_camera(frame[1]),
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
            
            camera.set_previous_status("Occupied")

        elif camera.status == "Vacant" and camera.previous_status == "Occupied":
            camera.presence_rate = 1 + camera.presence_rate

            camera.time_spent = get_working_time(camera.time_started)
            publish_to_mysql(camera.people_count, camera.station, camera.time_spent, camera.status, camera.previous_status, camera.sfvis, camera.presence_rate, camera.presence_total)
            time.sleep(0.5)
            
            camera.previous_status = "Vacant"
            camera.time_started = None
            camera.time_spent = None

def regular_post(camera):
    if (camera.check_time % 60) == 0:
        camera.presence_total = camera.presence_total + camera.presence_rate
        camera.presence_60 = camera.presence_rate
        camera.presence_rate = 0

    publish_to_mysql(camera.people_count, camera.station, None, camera.status, camera.previous_status, camera.sfvis, camera.presence_60, camera.presence_total)
    camera.pause = True

def main():
    sfvis = findSFVISno(hostname)
    model = initialize_model()

    print("How many cameras are you working with?")
    camera_amount = input()
    camera_group = [camera_amount]
    camera_id = [camera_amount]

    overall_time = time.time()

    try:
        for i in range(camera_amount):
            print("Where is the camera located at?")
            camera_id[i] = int(input("Camera " + i + ": "))

    except Error as err:
        print(f"Error in the user input: {err}")

    for i in range(camera_amount):
        cam_place = i + 1
        camera_group[i] = Camera(get_workstation(sfvis, cam_place), sfvis, "Vacant", None, "Vacant", 0, frame_rate, 0, 0, None, frame[i], initialize_camera(camera_id[i]), None, True, False, None, None, None)
        create_table(sfvis, camera_group[i].station)

        if camera_group[i].cap is None or model is None:
            return

    while True:
        for i in range(camera_amount):
            camera_group[i].ret, camera_group[i].frame = camera_group[i].cap.read()
            if not camera_group[i].ret:
                print("Error: Failed to read from the camera 1.")
                break
            
            frame[i] = camera_group[i].frame

            camera_group[i].cuda_img = jetson.utils.cudaFromNumpy(camera_group[i].frame)
            camera_group[i].detections = model.Detect(camera_group[i].cuda_img)
            camera_group[i].people_count = get_people_count(camera_group[i].detections)
            camera_group[i].status = get_workstation_status(camera_group[i].people_count)
            
            check_status(camera_group[i])

            check_time = int(time.time() - overall_time)

            if not camera_group[i].pause:
                if (check_time % 20) == 0:
                    camera_group[i].checkpoint = time.time()    
                    regular_post(camera_group[i])

            if camera_group[i].checkpoint is not None: 
                testing = time.time() - camera_group[i].checkpoint
                if str(f"{testing:.1f}") == "1.0":
                    camera_group[i].pause = False
                    camera_group[i].checkpoint = None

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    for i in range(camera_amount):
        camera_group[i].cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()