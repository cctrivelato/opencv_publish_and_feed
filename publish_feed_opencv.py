import cv2
import jetson.inference
import jetson.utils
import mysql.connector
import time
from datetime import datetime, timedelta
import threading
from flask import Flask, Response

frame_rate = 40

app = Flask(__name__)

frame1 = None
frame2 = None

# Initialize the camera using OpenCV
def initialize_camera(camera_id):
    cap = cv2.VideoCapture(camera_id)  # Open cameras
    if not cap.isOpened():
        print(f"Error: Could not open the camera {camera_id}.")
        return None
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1080)  # Lower resolution to reduce load
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
    global frame1
    while True:
        if frame1 is not None:
            ret, jpeg = cv2.imencode('.jpg', frame1)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

# Function to generate frames for Camera 2
def generate_camera_2():
    global frame2
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
def get_workstation(sfvis, camera_id):
    if camera_id == 0:
        workstation = (sfvis*2 - 1)
    elif camera_id == 2:
        workstation = (sfvis*2) 
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

# Function to publish count data to MySQL database (Non-blocking using threading)
def publish_to_mysql(people_count, station, time_spent, status, previous_status, sfvis, presence_rate, presence_total):
    def publish():
        db_config = {
            'user': 'admin',
            'password': 'CEll6505563!',
            'host': 'sfmysql02.sf.local',
            'database': 'test'
        }
        try:
            connection = mysql.connector.connect(**db_config)
            cursor = connection.cursor()

            # Insert query to the database
            if time_spent:
                query = ("INSERT INTO sfvis0" + str(sfvis) +"_cvdata"
                         "(Timestamp, WorkStation_Camera, Vision_System, Old_Status, Period_Status_last, New_Status, People_Count, Frame_Rate, Presence_Change_Total, Presence_Change_Rate) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
                data = (datetime.now(), station, sfvis, previous_status, time_spent, status, people_count, frame_rate, presence_total, presence_rate)

                query1 = ("INSERT INTO sfvis0" + str(sfvis) +"_grafdash"
                         "(Timestamp, WorkStation_Camera, Vision_System, Old_Status, Period_Status_last, New_Status, People_Count, Frame_Rate, Presence_Change_Total, Presence_Change_Rate) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
                data1 = (datetime.now(), station, sfvis, previous_status, time_spent, status, people_count, frame_rate, presence_total, presence_rate)
            else:
                query = ("INSERT INTO sfvis0" + str(sfvis) + "_cvdata"
                         "(Timestamp, WorkStation_Camera, Vision_System, Old_Status, New_Status, People_Count, Frame_Rate, Presence_Change_Total, Presence_Change_Rate) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                data = (datetime.now(), station, sfvis, previous_status, status, people_count, frame_rate, presence_total, presence_rate)
                
                query1 = ("INSERT INTO sfvis0" + str(sfvis) + "_grafdash"
                         "(Timestamp, WorkStation_Camera, Vision_System, Old_Status, New_Status, People_Count, Frame_Rate, Presence_Change_Total, Presence_Change_Rate) "
                         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
                data1 = (datetime.now(), station, sfvis, previous_status, status, people_count, frame_rate, presence_total, presence_rate)

            
            # Execute the DELETE query
            cursor.execute("DELETE FROM sfvis0" + str(sfvis) + "_grafdash ORDER BY Timestamp ASC LIMIT 1;")

            # Execute the query
            cursor.execute(query, data)
            cursor.execute(query1, data1)
            connection.commit()

            print(f"Published to MySQL: {people_count} people at Cam{station}")

        except mysql.connector.Error as err:
            print(f"Error: {err}")
        finally:
            if connection.is_connected():
                cursor.close()
                connection.close()

    # Run the publish function in a separate thread to avoid blocking
    threading.Thread(target=publish).start()

def check_status(people_count, station, status, time_started, previous_status, sfvis, presence_total, presence_rate):
    time_spent = None
    presence_total = 1 + presence_total

    if status == "Occupied" and previous_status == "Vacant":
        time_started = time.time()
        publish_to_mysql(people_count, station, time_spent, status, previous_status, sfvis, presence_rate, presence_total)
        previous_status = status

    elif status == "Vacant" and previous_status == "Occupied":
        time_spent = get_working_time(time_started)
        publish_to_mysql(people_count, station, time_spent, status, previous_status, sfvis, presence_rate, presence_total)
        previous_status = status
        time_started = None

    return status, time_started, previous_status, presence_rate, presence_total


def main():
    global frame1, frame2

    sfvis = 2  # This is the changing value
    camera_id1 = 0  # This value will never change
    camera_id2 = 4  # This value will never change, but check if it's correct

    # Initialize the camera and model
    cap1 = initialize_camera(camera_id1)
    cap2 = initialize_camera(camera_id2)
    model = initialize_model()

    if cap1 is None or cap2 is None or model is None:
        return
    
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)).start()

    previous_status1 = "Vacant"
    previous_status2 = "Vacant"
    time_started1 = None
    time_started2 = None
    first_time = True
    first_time2 = True
    pause = False

    presence_total1 = 0
    presence_total2 = 0
    presence_rate1 = 0
    presence_rate2 = 0
    delay1 = 0
    delay2 = 0

    overall_time = time.time()
    checkpoint = None

    while True:
        ret1, frame1 = cap1.read()
        if not ret1:
            print("Error: Failed to read from the camera 1.")
            break

        ret2, frame2 = cap2.read()
        if not ret2:
            print("Error: Failed to read from the camera 2.")
            break

        # Convert OpenCV frame to CUDA image
        cuda_img1 = jetson.utils.cudaFromNumpy(frame1)
        cuda_img2 = jetson.utils.cudaFromNumpy(frame2)

        # Run the object detection model
        detections1 = model.Detect(cuda_img1)
        detections2 = model.Detect(cuda_img2)

        # Count the number of people detected
        people_count1 = get_people_count(detections1)
        people_count2 = get_people_count(detections2)

        # Get the status of the welding booth
        status1 = get_workstation_status(people_count1)
        status2 = get_workstation_status(people_count2)

        # Get the welding booth
        station1 = get_workstation(sfvis, 0)
        station2 = get_workstation(sfvis, 2)

        # Check for change of status and publish information to the database
        if status1 != previous_status1:    
            if delay1 == 0:
                status1, time_started1, previous_status1, presence_rate1, presence_total1 = check_status(people_count1, station1, status1, time_started1, previous_status1, sfvis, presence_total1, presence_rate1)
            elif delay1 <= 49:
                delay1 = delay1 + 1
            else:
                status1, time_started1, previous_status1, presence_rate1, presence_total1 = check_status(people_count1, station1, status1, time_started1, previous_status1, sfvis, presence_total1, presence_rate1)
                delay1 = 0

        if status2 != previous_status2:    
            if delay2 == 0:
                status2, time_started2, previous_status2, presence_rate2, presence_total2 = check_status(people_count2, station2, status2, time_started2, previous_status2, sfvis, presence_total2, presence_rate2)
            elif delay2 <= 49:
                delay2 = delay2 + 1
            else:
                status2, time_started2, previous_status2, presence_rate2, presence_total2 = check_status(people_count2, station2, status2, time_started2, previous_status2, sfvis, presence_total2, presence_rate2)
                delay2 = 0

        check_time = int(time.time() - overall_time)
        
        if not pause:
            if (check_time % 20) == 0:
                checkpoint = time.time()
                if (check_time % 60) == 0:
                    if first_time:
                        presence_rate1 = presence_total1
                        first_time = False
                        old_presence_ttl1 = presence_total1
                    else:    
                        presence_rate1 = presence_total1 - old_presence_ttl1
                        old_presence_ttl1 = presence_total1

                    if first_time2:
                        presence_rate2 = presence_total2
                        first_time2 = False
                        old_presence_ttl2 = presence_total2
                    else:    
                        presence_rate2 = presence_total2 - old_presence_ttl2
                        old_presence_ttl2 = presence_total2

                publish_to_mysql(people_count1, station1, None, status1, previous_status1, sfvis, presence_rate1, presence_total1)
                publish_to_mysql(people_count2, station2, None, status2, previous_status2, sfvis, presence_rate2, presence_total2)
                pause = True

        if checkpoint is not None: 
            testing = time.time() - checkpoint
            if str(f"{testing:.1f}") == "1.0":
                pause = False
                checkpoint = None

        # Exit on 'q' key press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()