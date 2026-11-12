# Hệ thống chiếu sáng thông minh kết hợp AI nhận diện cử chỉ bàn tay

Đồ án môn IoT: ESP32 đọc cảm biến ánh sáng (LDR) và điều khiển 2 đèn LED (vàng, trắng). Máy tính dùng camera + AI nhận diện bàn tay (MediaPipe Hands) để điều khiển đèn từ xa qua MQTT. Giao diện web hiển thị trạng thái theo thời gian thực.

## 1. Tính năng

| Chế độ | Cách hoạt động |
|---|---|
| **Tự động** | Đèn sáng ngược với ánh sáng phòng: phòng tối thì đèn sáng, phòng sáng thì đèn tối (`đèn = 100 - ánh sáng`). Có thể đưa 1 tay vào camera để giả lập độ sáng phòng. |
| **Thủ công** | Tay trái chụm/mở ngón cái và ngón trỏ để chỉnh **đèn vàng**, tay phải chỉnh **đèn trắng** (chụm = 0%, mở rộng = 100%). |

## 2. Cấu trúc thư mục

```
cambienanhsang/
├── README.md
├── requirements.txt          # thư viện Python
├── .gitignore
├── esp32_wokwi/              # phần mạch giả lập trên Wokwi
│   ├── sketch.ino            # code ESP32
│   ├── diagram.json          # sơ đồ mạch
│   └── libraries.txt         # PubSubClient
└── smart_light/              # phần máy tính
    ├── main.py               # server Python: camera + AI + MQTT + API
    └── static/
        └── index.html        # giao diện web
```

## 3. Kiến trúc hệ thống

```
 Camera ──► Python (MediaPipe) ──publish──► MQTT broker ──► ESP32 (Wokwi) ──► LED vàng / LED trắng
              │  ▲                          (broker.emqx.io)      ▲
              │  └────────── subscribe ◄─────────────────────────┘ gửi dữ liệu LDR + trạng thái đèn
              ▼
        FastAPI  ◄──► Trình duyệt (index.html), hỏi /api/status mỗi 0.3 giây
```

Hai topic MQTT (tiền tố `thang_smartlight_8421`, **phải giống nhau ở cả ESP32 và Python**):

| Topic | Hướng | Nội dung |
|---|---|---|
| `thang_smartlight_8421/cmd` | Python → ESP32 | Lệnh điều khiển |
| `thang_smartlight_8421/data` | ESP32 → Python | Dữ liệu cảm biến, JSON |

Các lệnh trên topic `cmd`:

| Lệnh | Ý nghĩa |
|---|---|
| `MODE:AUTO` / `MODE:MANUAL` | Chọn chế độ |
| `S:80,30` | Thủ công: đèn vàng 80%, đèn trắng 30% (1 lệnh gộp cho 2 đèn) |
| `A:60` | Tự động: giả lập độ sáng phòng 60% theo cử chỉ tay |
| `A:LDR` | Tự động: quay lại dùng cảm biến LDR thật |

Dữ liệu ESP32 gửi lên topic `data`:

```json
{"raw":1001,"light":75,"y":25,"w":25,"mode":"AUTO"}
```
`raw` là giá trị ADC thô (0–4095), `light` là độ sáng phòng (%), `y`/`w` là độ sáng đèn vàng/trắng (%).

## 4. Đấu nối mạch (Wokwi)

| Linh kiện | Chân linh kiện | Chân ESP32 |
|---|---|---|
| Module cảm biến ánh sáng LDR | VCC | 3V3 |
| | GND | GND |
| | AO (analog) | **GPIO 34** |
| LED vàng | Anode (qua điện trở hạn dòng) | **GPIO 26** |
| LED trắng | Anode (qua điện trở hạn dòng) | **GPIO 27** |
| Cả 2 LED | Cathode | GND |

GPIO 34 chỉ là chân đầu vào (input only), phù hợp để đọc ADC.

## 5. Giải thích code ESP32 (`esp32_wokwi/sketch.ino`)

1. **Khai báo**: địa chỉ broker, 2 topic, 3 chân (`PIN_LDR=34`, `PIN_Y=26`, `PIN_W=27`).
2. **`setLamp(pin, channel, pct)`**: đổi % (0–100) sang duty PWM 8 bit (0–255) để điều chỉnh độ sáng LED. Có 2 nhánh code cho ESP32 core v2 và v3.
3. **`handleCmd(cmd)`**: đọc lệnh từ Python (bảng lệnh ở mục 3) và cập nhật biến `autoMode`, `yPct`, `wPct`, `handLight`.
4. **`callback(...)`**: được gọi khi có tin nhắn đến topic `cmd`, xử lý ngay (không dùng hàng đợi để tránh mất lệnh).
5. **`connectWifi()` / `connectMqtt()`**: nối WiFi `Wokwi-GUEST`, nối broker, đăng ký topic `cmd`. Client ID ngẫu nhiên để tránh bị broker đá ra khi trùng.
6. **`loop()`** chạy liên tục:
   - Giữ kết nối WiFi/MQTT (thử lại, không chặn việc điều khiển đèn).
   - Đọc LDR: `raw = analogRead(34)`, đổi sang `light` (%): `raw` càng thấp thì càng sáng.
   - Nếu chế độ tự động: `yPct = wPct = 100 - light`.
   - Xuất PWM ra 2 LED.
   - Gửi JSON lên topic `data` khi có thay đổi (tối đa 10 lần/giây) hoặc mỗi 0,5 giây.

## 6. Giải thích code Python (`smart_light/main.py`)

| Phần | Vai trò |
|---|---|
| `State` | Lưu trạng thái dùng chung: chế độ, tay nào đang thấy, % của từng tay, dữ liệu ESP32, nhật ký. |
| MQTT (`on_connect`, `on_message`) | Nối broker, nhận dữ liệu ESP32, ghi nhận ESP32 online/offline (`ONLINE_TIMEOUT` = 15 giây). |
| `loop()` (chạy ở luồng riêng) | Đọc camera → MediaPipe tìm 21 điểm mốc của bàn tay → tính khoảng cách ngón cái (điểm 4) và ngón trỏ (điểm 8) chia cho chiều dài lòng bàn tay (điểm 0→9) → chuẩn hóa thành 0–100%. Làm mượt bằng bộ lọc `0.2*cũ + 0.8*mới`. |
| `send_both()` | Chế độ thủ công: gộp 2 tay thành 1 lệnh `S:y,w`, giới hạn 20 lệnh/giây. |
| `send_ambient()` / `release_ambient()` | Chế độ tự động: gửi `A:xx` khi có tay, gửi `A:LDR` khi rút tay. |
| API FastAPI | `/api/start`, `/api/stop` (bật/tắt camera), `/api/mode` (đổi chế độ), `/api/status` (trạng thái cho web), `/video` (luồng camera MJPEG). |

## 7. Giải thích giao diện (`smart_light/static/index.html`)

- Gọi `/api/status` mỗi 0,3 giây rồi vẽ lại giao diện (hàm `poll`).
- `showMode()` ẩn/hiện khu vực **Tự động** (thanh ánh sáng phòng) và **Thủ công** (2 thanh tay trái/phải) ngay khi bấm, không chờ ESP32.
- Hai bóng đèn SVG đổi độ sáng theo %; khối "Phòng mô phỏng" thể hiện ánh sáng phòng; tab Dashboard vẽ biểu đồ 2 phút gần nhất bằng canvas.

## 8. Cách chạy

**Yêu cầu**: Python 3.11, webcam, tài khoản Wokwi (miễn phí).

**Bước 1: ESP32 trên Wokwi**
1. Vào wokwi.com, tạo project ESP32, dán `sketch.ino` và `diagram.json`, thêm thư viện `PubSubClient` ở tab Library Manager.
2. Bấm ▶. Serial Monitor phải hiện `WiFi OK` rồi `MQTT... OK`.

**Bước 2: Python**
```bash
python -m venv venv311
venv311\Scripts\activate        # Windows
pip install -r requirements.txt
python smart_light/main.py
```

**Bước 3: Mở web** tại http://127.0.0.1:8001, bấm **Bật camera**, chọn chế độ rồi thử cử chỉ tay.

## 9. Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Serial Wokwi `WiFi... FAIL` | Chạy lại simulation, tải lại trang, tắt VPN/extension chặn quảng cáo, hoặc đổi sang 4G điện thoại. |
| `MQTT... FAIL rc=-2` | Đổi broker (`broker.hivemq.com`, `test.mosquitto.org`, `broker.emqx.io`) ở **cả hai** file. |
| Web báo ESP32 "Mất kết nối" | Để tab Wokwi hiện trên màn hình (tab chạy nền bị trình duyệt làm chậm). |
| Đèn trễ | Wokwi chạy chậm hơn thời gian thực và broker công cộng có độ trễ; chạy ESP32 thật sẽ nhanh hơn. |
| Lỗi `mp.solutions` | Cài `mediapipe==0.10.14` (bản mới hơn đã đổi API). |

## 10. Công nghệ sử dụng

ESP32 (Arduino), Wokwi, MQTT (PubSubClient, paho-mqtt), Python, FastAPI, OpenCV, MediaPipe Hands, HTML/CSS/JavaScript.
