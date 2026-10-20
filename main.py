"""screen.render() の結果を ACEMAGIC S1 のフロントLCDに表示し続ける。

  python main.py              # LCDに表示
  python main.py --preview    # LCDに送らず preview.png に書き出す (表示確認用)
"""
import argparse
import signal
import sys
import time

import screen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="preview.png に保存して終了")
    args = ap.parse_args()

    if args.preview:
        size = (170, 320) if screen.PORTRAIT else (320, 170)
        screen.render(size).save("preview.png")
        print("preview.png を保存しました")
        return

    from lcd import S1LCD

    lcd = S1LCD(portrait=screen.PORTRAIT)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    last_draw = 0.0
    try:
        while True:
            now = time.monotonic()
            if now - last_draw >= screen.INTERVAL:
                lcd.redraw(screen.render(lcd.size))
                last_draw = now
            time.sleep(0.2)
            lcd.heartbeat()
            time.sleep(0.8)
    finally:
        lcd.close()


if __name__ == "__main__":
    main()
