import pyrealsense2 as rs
from networktables import NetworkTables
import threading
import grip
import cv2
import numpy as np
import data_process
import math
import sys
# import cscore as cs  UNCOMMENT

WIDTH = 640
HEIGHT = 480
H_FOV = 53.13 # need to recalculate if change WIDTH dimension  (line up meter stick and get distance then atan)
F_LENGTH = 0.00193 # in meters
SENSOR_WIDTH = 0.003549 # in meter

grip_pipe = grip.GreenProfile()

cond = threading.Condition() #global for network tables
notified = [False]

def connectionListener(connected, info):

    print(info, '; Connected=%s' % connected)
    with cond:
        notified[0] = True
        cond.notify()

def startNetworkTables():

    NetworkTables.startClientTeam(668)
    NetworkTables.initialize(server='10.6.68.2') #roborio must be on this static ip
    NetworkTables.addConnectionListener(connectionListener, immediateNotify=True)

    with cond:
        print("Waiting")
        if not notified[0]:
            cond.wait()

    print("Connected!")

# dist1 will always be the leftmost point and dist2 will always be the rightmost
# TODO: does it make sense to return -1 if missed point, or the last valid point
def getOrientationAngle(dist1, dist2, dist_center, yaw): # has to be here because need depths
    tape_dist = 0.2985 # in meters to match other units, 11.75 inches
    tape_dist /= 2.0
    # print("dist1: " + str(dist1))
    # print("dist2: " + str(dist2))
    # print("dist_center: " + str(dist_center))
    # print("tape_dist: " + str(tape_dist))
    print("yaw: " + str(yaw))
    # Right = +theta
    # Left = -theta
    if dist2 == 0 or dist1 == 0:
        return -1

    cos_expression = (dist * dist - tape_dist * tape_dist - dist2 * dist2) / (-2.0 * tape_dist * dist2)

    # out of domain
    if cos_expression >= 1 or cos_expression <= -1:
        return -1

    if dist1 > dist2:
        return (90.0 - yaw - math.degrees(math.acos(cos_expression)))

    return -(90.0 - yaw - math.degrees(math.acos(cos_expression)))


try:
    # startNetworkTables() UNCOMMENT
    # table = NetworkTables.getTable('SmartDashboard') UNCOMMENT

    counter = 0 # used to take intervals of exit angle data
    exit_angles = []

    pipe = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, int(WIDTH), int(HEIGHT), rs.format.bgr8, 60) #numbers that work: 6, 15
    config.enable_stream(rs.stream.depth, int(WIDTH), int(HEIGHT), rs.format.z16, 60)
    pipe.start(config)

    dp = data_process.DataProcess(grip_pipe, H_FOV, F_LENGTH, SENSOR_WIDTH, WIDTH, HEIGHT)

#    cam = cs.UsbCamera("webcam", 0)
    # cserver = cs.CameraServer() UNCOMMENT

    # src = cs.CvSource("server", cs.VideoMode.PixelFormat.kMJPEG, WIDTH, HEIGHT, 70) UNCOMMENT
    # cserver.startAutomaticCapture(camera=src) UNCOMMENT
    while True:
        frames = pipe.wait_for_frames()
        depth = frames.get_depth_frame()
        color = frames.get_color_frame()
        if not (color and depth):
            continue

        img = np.asarray(color.get_data())
        grip_pipe.process(img)

        dp.update(img)
        left = int(dp.cx)
        down = int(dp.cy)
        # dist = depth.get_distance(int(WIDTH / 2), int(HEIGHT / 2))
        dist1 = 0.0
        dist2 = 0.0

        # Make sure that dist1 is on the left and dist2 is on the right
        if dp.x1 < dp.x2:
            dist1 = depth.get_distance(int(dp.x1), int(dp.y1))
            dist2 = depth.get_distance(int(dp.x2), int(dp.y2))
        else:
            dist2 = depth.get_distance(int(dp.x1), int(dp.y1))
            dist1 = depth.get_distance(int(dp.x2), int(dp.y2))

        dist = (dist1 + dist2) / 2

        exit_angles.append(getOrientationAngle(dist1, dist2, dist, dp.angle))
        counter += 1


        print("dist: " + str(dist))
        print("yaw ang: " + str(dp.angle))
        print("exit ang: " + str(exit_angles[len(exit_angles) - 1]) + "\n")

        if not dp.isTapeDetected:
            dist = -1
            dp.angle = -1


        table.putNumber('depth', dist)
        table.putNumber('yaw', dp.angle +)

        # TODO account for -1 issue (repeating, corrupting data)
        if counter >= 50: # analyze exit angle data in groups of x, should only take a little longer than x milliseconds (waitKey(milliseconds) + procesing time)
            final_exit_angle = dp.noramlizeData(exit_angles)
            table.putNumber('exit_angle', final_exit_angle)
            counter = 0
            exit_angles = []

        src.putFrame(img)


        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("leave")
            break

except Exception as e:
    print(e)
finally:
    pipe.stop()
    cv2.destroyAllWindows()
    # Method calls agaisnt librealsense objects may throw exceptions of type pylibrs.error
    # print("pylibrs.error was thrown when calling %s(%s):\n" % (e.get_failed_function(), e.get_failed_args()))
    # print("    %s\n", e.what())
    exit(1)
