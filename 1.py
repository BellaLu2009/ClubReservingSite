import time
import threading
from pynput import mouse, keyboard

# ========== 配置参数 ==========
CLICK_INTERVAL = 0.01      # 点击间隔（秒），数值越小越快
TOGGLE_KEY = keyboard.Key.f2   # 开关按键
EXIT_KEY = keyboard.Key.esc     # 退出按键
# =============================

class AutoClicker:
    def __init__(self):
        self.clicking = False
        self.running = True
        self.thread = None
        self.mouse_controller = mouse.Controller()

    def click_loop(self):
        """独立线程执行连点"""
        while self.running:
            if self.clicking:
                self.mouse_controller.click(mouse.Button.left)
                # time.sleep(CLICK_INTERVAL)
            else:
                time.sleep(0.01)

    def toggle(self):
        """切换连点状态"""
        self.clicking = not self.clicking
        if self.clicking:
            print("\033[92m▶️ 自动点击已启动 (再次按 F2 暂停)\033[0m")
        else:
            print("\033[91m⏸️ 自动点击已暂停\033[0m")

    def stop(self):
        """停止程序"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)
        print("\033[93m🛑 程序已退出\033[0m")


def on_press(key):
    """键盘按下事件回调"""
    try:
        if key == TOGGLE_KEY:
            clicker.toggle()
        elif key == EXIT_KEY:
            clicker.stop()
            return False  # 停止键盘监听
    except Exception as e:
        print(f"⚠️ 按键处理错误: {e}")


if __name__ == "__main__":
    # 检查依赖
    try:
        from pynput import mouse, keyboard
    except ImportError:
        print("❌ 缺少 pynput 库，请运行：")
        print("pip install pynput -i https://pypi.tuna.tsinghua.edu.cn/simple")
        exit(1)

    print("=" * 55)
    print("🖱️  F2 快速连点器 (pynput 稳定版)")
    print("=" * 55)
    print(f"📌 按 F2 键 开始/暂停 自动点击")
    print(f"⚡ 点击间隔: {CLICK_INTERVAL * 1000:.0f} 毫秒")
    print(f"❌ 按 ESC 键 退出程序")
    print("💡 如果无效，请检查终端是否有辅助功能权限")
    print("=" * 55)

    clicker = AutoClicker()

    # 启动连点线程
    clicker.thread = threading.Thread(target=clicker.click_loop, daemon=True)
    clicker.thread.start()

    # 启动键盘监听（阻塞式）
    with keyboard.Listener(on_press=on_press) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            clicker.stop()
            print("\n程序被用户中断")