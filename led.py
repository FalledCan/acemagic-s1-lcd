"""ACEMAGIC S1 前面 LED (CH340 シリアル /dev/ttyUSB0) ドライバ

プロトコルは https://github.com/tjaworski/AceMagic-S1-LED-TFT-Linux の解析に基づく。
5 バイト: 0xFA, テーマ, 明るさ, 速さ, チェックサム (前の4バイトの和の下位8ビット)
明るさ・速さはデバイス上の値が 1=最大 〜 5=最小 なので、ここでは 1〜5 (5 が最大) で受けて反転する。
"""
import time

import serial

DEVICE = "/dev/ttyUSB0"
BAUD = 10000

THEMES = {
    "rainbow": 0x01,
    "breathing": 0x02,
    "cycle": 0x03,
    "off": 0x04,
    "auto": 0x05,
}


def _level(n):
    return min(5, max(1, 6 - int(n)))


def set_led(theme, brightness=3, speed=3, device=DEVICE):
    cmd = [0xFA, THEMES[theme], _level(brightness), _level(speed)]
    cmd.append(sum(cmd) & 0xFF)
    with serial.Serial(device, BAUD, timeout=1) as port:
        # 参考実装と同じく 1 バイトずつ 5ms あけて送る
        for b in cmd:
            port.write(bytes([b]))
            port.flush()
            time.sleep(0.005)


if __name__ == "__main__":
    import sys

    set_led(sys.argv[1] if len(sys.argv) > 1 else "off", *map(int, sys.argv[2:4]))
