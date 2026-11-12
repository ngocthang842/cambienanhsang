import paho.mqtt.client as mqtt

TOPIC = "thang_smartlight_8421/data"

def on_connect(c, u, f, rc, p=None):
    print("Da ket noi broker, ma =", rc)
    c.subscribe(TOPIC)

def on_message(c, u, m):
    print("NHAN:", m.payload.decode())

cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
cl.on_connect = on_connect
cl.on_message = on_message
cl.connect("broker.hivemq.com", 1883, 60)
cl.loop_forever()