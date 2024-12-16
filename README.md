This is the setup for the OpenCV for the Jetson Orin Nano.

The setup counts with collection of several data points when running code 'publish_feed_opencv.py' at the Orin - which file should be present in the same folder as 'webpage_setup.html'. 

Three folders are present in this repository:

1. starting_package. Made to carry all the main files that can set an Orin Nano ready to go. Ready to collect data, publish it, and set up the page where the feed of the camera is posted.

2. testing. For all the files that are in enhancement and fixes prior to officially update the main files.

3. weblink_dashboard. For files that support the main function of the Vision System. They are both the webpage in u-format to access data post and/or camera feeds and the json file that contains the template for Grafana Dashboards to share data from the Vision System.
