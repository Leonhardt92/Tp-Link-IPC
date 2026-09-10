
from flask import Flask, render_template, jsonify
from onvif import ONVIFCamera
import json, os, subprocess, platform, requests, zipfile, shutil

app=Flask(__name__)

with open("config/camera.json") as f:
    cfg=json.load(f)

go2rtc_process=None

def cam():
    c=cfg["camera"]
    return ONVIFCamera(c["ip"], c["onvif_port"], c["username"], c["password"])

def get_rtsp():
    m=cam().create_media_service()
    p=m.GetProfiles()[0]
    req=m.create_type("GetStreamUri")
    req.StreamSetup={
        "Stream":"RTP-Unicast",
        "Transport":{"Protocol":"RTSP"}
    }
    req.ProfileToken=p.token
    return m.GetStreamUri(req).Uri

def start_go2rtc():
    global go2rtc_process
    if go2rtc_process:
        return
    os.makedirs("runtime",exist_ok=True)
    binary="runtime/go2rtc"
    if not os.path.exists(binary):
        if platform.system()=="Darwin":
            name="go2rtc_mac_amd64.zip"
            url="https://github.com/AlexxIT/go2rtc/releases/latest/download/"+name
            data=requests.get(url,timeout=60).content
            open("runtime/a.zip","wb").write(data)
            with zipfile.ZipFile("runtime/a.zip") as z:
                z.extractall("runtime")
            for x in os.listdir("runtime"):
                if x.startswith("go2rtc") and x!="go2rtc":
                    shutil.move("runtime/"+x,binary)
                    break
        os.chmod(binary,0o755)

    go2rtc_process=subprocess.Popen([binary,"-c","config/go2rtc.yaml"])

def init_stream():
    rtsp=get_rtsp()
    with open("config/go2rtc.yaml","w") as f:
        f.write(f"""
streams:
  ipc:
    - {rtsp}

api:
  listen: 127.0.0.1:1984
""")
    if go2rtc_process:
        go2rtc_process.terminate()
    start_go2rtc()

@app.route("/")
def index():
    init_stream()
    return render_template("index.html")

@app.route("/info")
def info():
    d=cam().create_devicemgmt_service().GetDeviceInformation()
    return jsonify({
        "model":d.Model,
        "firmware":d.FirmwareVersion,
        "serial":d.SerialNumber
    })

@app.route("/position")
def position():
    m=cam().create_media_service()
    p=m.GetProfiles()[0]
    s=cam().create_ptz_service().GetStatus({"ProfileToken":p.token})
    return jsonify({
        "x":s.Position.PanTilt.x,
        "y":s.Position.PanTilt.y,
        "move":str(s.MoveStatus.PanTilt)
    })

@app.route("/ptz/<cmd>",methods=["POST"])
def ptz(cmd):
    m=cam().create_media_service()
    p=m.GetProfiles()[0]
    s=cam().create_ptz_service()

    if cmd=="stop":
        s.Stop({"ProfileToken":p.token,"PanTilt":True,"Zoom":False})
        return "ok"

    r=s.create_type("ContinuousMove")
    r.ProfileToken=p.token
    x=y=0
    if cmd=="left": x=-0.5
    if cmd=="right": x=0.5
    if cmd=="up": y=0.5
    if cmd=="down": y=-0.5

    if cfg["ptz"]["reverse_x"]: x=-x
    if cfg["ptz"]["reverse_y"]: y=-y

    r.Velocity={"PanTilt":{"x":x,"y":y}}
    s.ContinuousMove(r)
    return "ok"

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8080)
