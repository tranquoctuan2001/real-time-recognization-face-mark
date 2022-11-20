# from PIL import Image
from asyncio.windows_events import NULL
from flask import Flask
from flask import request
from datetime import datetime
# from time import gmtime, strftime
import os
import cv2
import numpy as np
import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import json
import time
import base64
from PIL import Image

# Create Flask Server Backend
app = Flask(__name__)

# load label
app.config['UPLOAD_FOLDER'] = "RecievedImg"
app.config['LABEL'] = "RecievedLabel"
app.config['VIDEO'] = "RecievedVideo"
cred = credentials.Certificate('./authentication.json')
default_app = firebase_admin.initialize_app(cred, {
    'databaseURL': "https://project-realtime-161a1-default-rtdb.firebaseio.com/"})

ref = db.reference("/")
print(default_app.name)
# ref.set({
#     "recognizations":
#     {
#         "face_mark": -1
#     }
# })
ref = db.reference("/recognizations/face_mark")


def makeDir(dir):
    if not os.path.exists(dir):
        os.makedirs(dir)


makeDir(app.config['UPLOAD_FOLDER'])
makeDir(app.config['LABEL'])
makeDir(app.config['VIDEO'])

formatDatetime = '%d-%m-%Y_%H-%M-%S-%f'
skipTime = 4
classes_file = "data/obj.names"
with open(classes_file, 'r') as f:
    classes = [line.strip() for line in f.readlines()]
# color green vs red
colors = [(0, 255, 0), (0, 0, 255)]
# file model vs config
modelcfg = "cfg/yolov4.cfg"
weight = "Model/yolov4-custom_best.weights"
# Load model
net = cv2.dnn.readNet(weight, modelcfg)
# net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
# net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]


def saveFile(dir, file, name, extension):
    path_to_save = os.path.join(dir, f"{name}.{extension}")
    try:
        cv2.imwrite(path_to_save, file)
    except:
        file.save(path_to_save)
    return path_to_save


def detect(iH, iW, outs):
    class_ids = []
    confidences = []
    boxes = []
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            if confidence > 0.7:
                center_x = int(detection[0] * iW)
                center_y = int(detection[1] * iH)
                w = int(detection[2] * iW)
                h = int(detection[3] * iH)
                x = center_x - w / 2
                y = center_y - h / 2
                class_ids.append(class_id)

                confidences.append(float(confidence))
                boxes.append([x, y, w, h])
    return class_ids, confidences, boxes

# draw


def draw(img, class_id, confidence, x, y, x_plus_w, y_plus_h):
    label = str(classes[class_id])+" (" + str(round(confidence*100, 2)) + "%)"
    cv2.rectangle(img, (x, y), (x_plus_w, y_plus_h), colors[class_id], 2)
    cv2.putText(img, label, (x-10, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[class_id], 2)

# App default


@app.route('/', methods=['POST', 'GET'])
def image():
    if request.method == 'POST':
        # Take request
        name = f"{datetime.now().strftime(formatDatetime)}"
        print(f"from: {name}")
        img = request.files['file']
        file_bytes = np.fromfile(img, np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

        res = []

        print(f"to:   {datetime.now().strftime(formatDatetime)}")
        # build
        blob = cv2.dnn.blobFromImage(
            image, 1 / 255.0, (416, 416), swapRB=True, crop=False)
        net.setInput(blob)
        outs = net.forward(output_layers)

        print(f"to:   {datetime.now().strftime(formatDatetime)}")
        # detect
        class_ids, confidences, boxes = detect(
            image.shape[:2][0], image.shape[:2][1], outs)
        # take index in list
        indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        info = ""
        for i in indexes:
            lst = []
            # append label
            label = str(classes[class_ids[i]])
            lst.append(label)
            # append x, y, weight, height
            x, y, w, h = boxes[i]
            lst.extend(boxes[i])
            # append confidences
            lst.append(confidences[i])
            res.append(lst)

            info += f"{class_ids[i]} {x} {y} {w} {h}\n"

            nowTime = int(time.time())
            insertData(x, y, w, label, nowTime, img.filename)
        pathsave = os.path.join(app.config['LABEL'], f"{name}.txt")

        if os.listdir(app.config['UPLOAD_FOLDER']):
            last = datetime.strptime(os.listdir(
                app.config['UPLOAD_FOLDER'])[-1].split('.')[0], formatDatetime)
        else:
            last = datetime.min
        now = datetime.strptime(name, formatDatetime)

        if info != "" and [value for value in confidences if value < 0.9] == [] and (now-last).seconds > skipTime:
            # save image
            path_to_save = saveFile(
                app.config['UPLOAD_FOLDER'], image, name, "jpg")
            re = cv2.imread(path_to_save)
            f = open(pathsave, "w")
            # save label
            f.write(info)
            f.close()
        print(f"to:   {datetime.now().strftime(formatDatetime)}")
        return res
    return {}


@app.route('/video', methods=['POST'])
def video():
    name = f"{datetime.now().strftime(formatDatetime)}"
    print(f"from: {name}")
    vid = request.files['file']

    path_to_save = saveFile(
        app.config['VIDEO'], vid, vid.filename.split('.')[0], "mp4")
    # path_to_save = saveFile(app.config['VIDEO'],vid, name, "mp4")
    video = cv2.VideoCapture(path_to_save)

    while True:
        _, frame = video.read()

        blob = cv2.dnn.blobFromImage(
            frame, 1 / 255.0, (416, 416), swapRB=True, crop=False)
        net.setInput(blob)
        outs = net.forward(output_layers)

        class_ids, confidences, boxes = detect(
            frame.shape[:2][0], frame.shape[:2][1], outs)
        indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)

        # draw
        for i in indexes:
            x, y, w, h = boxes[i]
            # draw box
            draw(frame, class_ids[i], confidences[i], round(
                x), round(y), round(x + w), round(y + h))
        cv2.imshow("Image", frame)
        key = cv2.waitKey(1)
        if key == 27:
            break
    video.release()

    print(f"to:   {datetime.now().strftime(formatDatetime)}")
    return path_to_save


@app.route('/get-all-data', methods=['GET'])
def getAllData():
    print(ref.get())
    return "success"


def insertData(x, y, w, label, nowTime, img):
    ref.push().set({
        'x': x,
        'y': y,
        'w': w,
        'label': label,
        'time': nowTime,
        'image': img
    })


# Start Backend
if __name__ == '__main__':
    app.run(port=30701)