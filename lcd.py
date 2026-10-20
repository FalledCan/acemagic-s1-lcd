"""ACEMAGIC S1 フロントLCD (USB 04d9:fd01, interface 1) ドライバ

プロトコルは https://github.com/tjaworski/AceMagic-S1-LED-TFT-Linux の解析に基づく。
- 解像度 320x170, RGB565 (ビッグエンディアン)
- 1回の送信は常に 4104 バイト (ヘッダ 8 + データ 4096) を EP 0x02 へ
- 全画面描画は 27 チャンク (26 x 4096 + 2304 = 108800 バイト)
"""
import time
from datetime import datetime

import usb.core
import usb.util

VID, PID = 0x04D9, 0xFD01
INTERFACE = 1
EP_OUT = 0x02

WIDTH, HEIGHT = 320, 170
BUFFER_SIZE = 4104
HEADER_SIZE = 8
DATA_SIZE = 4096
CHUNK_COUNT = 27
FINAL_CHUNK_SIZE = 2304


def to_rgb565(img):
    """PIL Image -> RGB565 big-endian bytes"""
    img = img.convert("RGB")
    out = bytearray(img.width * img.height * 2)
    i = 0
    for r, g, b in img.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[i] = v >> 8
        out[i + 1] = v & 0xFF
        i += 2
    return bytes(out)


class S1LCD:
    def __init__(self, portrait=False):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError("LCD (04d9:fd01) が見つかりません")
        try:
            if self.dev.is_kernel_driver_active(INTERFACE):
                self.dev.detach_kernel_driver(INTERFACE)
        except (NotImplementedError, usb.core.USBError):
            pass
        usb.util.claim_interface(self.dev, INTERFACE)
        self.portrait = portrait
        self.set_orientation(portrait)
        self.heartbeat()

    @property
    def size(self):
        return (HEIGHT, WIDTH) if self.portrait else (WIDTH, HEIGHT)

    def _send(self, buf):
        self.dev.write(EP_OUT, bytes(buf), timeout=1000)

    def set_orientation(self, portrait):
        buf = bytearray(BUFFER_SIZE)
        buf[0:4] = bytes([0x55, 0xA1, 0xF1, 0x02 if portrait else 0x01])
        self._send(buf)
        time.sleep(0.05)

    def heartbeat(self):
        """時刻を送る。参考実装では約1秒ごとに送ってキープアライブにしている"""
        now = datetime.now()
        buf = bytearray(BUFFER_SIZE)
        buf[0:6] = bytes([0x55, 0xA1, 0xF2, now.hour, now.minute, now.second])
        self._send(buf)

    def redraw(self, img):
        """全画面描画。img は self.size の PIL Image"""
        if img.size != self.size:
            img = img.resize(self.size)
        if self.portrait:
            # フレームバッファは常に 320x170。縦向きは反時計回りに 90° 回して送る (参考実装と同じ)
            img = img.rotate(90, expand=True)
        pixels = to_rgb565(img)
        buf = bytearray(BUFFER_SIZE)
        buf[0] = 0x55
        buf[1] = 0xA3
        for idx in range(CHUNK_COUNT):
            length = DATA_SIZE if idx < CHUNK_COUNT - 1 else FINAL_CHUNK_SIZE
            buf[2] = 0xF0 if idx == 0 else (0xF2 if idx == CHUNK_COUNT - 1 else 0xF1)
            buf[3] = idx + 1
            offset = (idx * DATA_SIZE) & 0xFFFF
            buf[5] = offset >> 8
            buf[6] = offset & 0xFF
            buf[7] = length >> 8
            start = idx * DATA_SIZE
            buf[HEADER_SIZE:HEADER_SIZE + DATA_SIZE] = bytes(DATA_SIZE)
            buf[HEADER_SIZE:HEADER_SIZE + length] = pixels[start:start + length]
            self._send(buf)

    def close(self):
        usb.util.release_interface(self.dev, INTERFACE)
        usb.util.dispose_resources(self.dev)
