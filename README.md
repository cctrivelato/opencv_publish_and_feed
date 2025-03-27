This is the setup for the OpenCV for the Jetson Orin Nano.

The setup counts with collection of several data points when running code 'sfvis.py' at the Orin - which file should be present in the same folder as 'webpage_setup.html'. 

Three folders are present in this repository:

1. /starting_package: Folder made to carry all the main files that can set an Orin Nano ready to go. Ready to install dependencies first, collect data, publish it, and set up the page where the feed of the camera is posted. Just remembering that there is a need to run install dependencies first, edit information on dbconfig.ini (for database credentials), then run sfvis.py. Using local IP address as url with port :5000/camera1 or :5000/camera2 can connect you to camera feed.

2. /testing: Folder made for all the files that are in process of development/enhancement and fixes before the main files can be officially update.

3. weblink_dashboard. Folder made for files that support the main function of the Vision System. There are two important files. One is the html file for the main webpage with a "main" tag in U-format with url in buttons to access data points displayed on Grafana dashboards and/or camera feeds. The other is a json file that contains the template for Grafana Dashboards to collect data from MySQL Database and create a visualization for the data from the Vision System.
