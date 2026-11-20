# ✨ MouseFX

<p align="center"><img src="assets/icon.png" width="120" alt="MouseFX icon"></p>

**A lightweight Windows cursor effects overlay** · 6 styles · trails · falling sakura · ink wash + full 13-slot system cursor replacement · single exe, no install

[🇺🇸 English](#english) | [🇨🇳 中文](#中文简介)

---

## English

**MouseFX** is a fun, lightweight system-wide cursor effects utility for Windows that I built with **AI-assisted development**, powered by Python and PyQt6 🚀. Zero external image assets needed—just pure, silky desktop magic running quietly in the background ✨!

### 🎨 What's Cool About It?

* ⚡ **Buttery Smooth at 240Hz & Multi-Monitor Ready**: Delta-time physics keep animations silky at high refresh rates across all your monitors. Choose whether effects float over every window or chill strictly on the desktop layer.
* 🪄 **Effects + Full Custom Cursor Sets**: Switch between 6 artistic vibes (Ambient Spotlight, Constellation Web, Magnetic Ring, Ink Wash, Optical Prism, and Falling Sakura 🌸) with matching 13-slot Windows system cursors—everything snaps cleanly back to your default cursors when paused or closed.
* 🎛️ **Stackable Extras & Free Color Tuning**: Left-click the tray icon to pop open the control panel—layer on silk ribbon trails, Kelvin water-wake ripples 🌊, a taskbar-safe flashlight dark mask 🔦, or demo click ripples, plus custom color picking 🎨 and one-click presets.
* 🛡️ **Zero-Hassle Daily Driver**: Comes with single-instance protection, automatic pause during fullscreen games or videos 🎮, persistent local settings, and optional Windows startup launch.

### 🚀 Quick Start

* **Grab the `.exe` directly**: Don't want to set up Python? Just head over to **Releases** on the right and download `MouseFX.exe` from the attachments—double-click and enjoy 🎉!
* **Run from source** (Windows 10 / 11, Python 3.10+):

```bash
# 1. Install PyQt6
pip install PyQt6

# 2. Launch right away
python windows_mouse_fx.py
```

* **Build your own `.exe`**:

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name MouseFX windows_mouse_fx.py
```

Left-click the system tray icon anytime to tweak your setup! 🖱️✨

> ⚠️ Windows may show "Windows protected your PC" on first launch — click **More info → Run anyway**.

### 🆘 Cursors stuck?

If MouseFX got killed, cursors may stay customized:

* Relaunch MouseFX 🧹
* Run `MouseFX.exe --restore` ⚡
* Or log off / reboot

---

## 中文简介

**MouseFX** 是我借助 **AI 辅助开发**出来的一款 Windows 全局桌面鼠标美化小工具，用 Python + PyQt6 写成 🚀。零外部图片素材、不挑桌面环境，开箱即用，在后台默默给你的鼠标加点魔法 ✨！

### 🎨 有什么好玩的？

* ⚡ **高刷跟手、多屏随便滑**：专为高刷屏调校（240Hz 也丝般顺滑），多显示器无缝跨屏，想让特效浮在所有窗口上面还是只留在桌面底层都能一键切换。
* 🪄 **特效 + 全套指针一起换**：内置柔光氛围光晕、蛛网引力连线、极简磁力光环、水墨丹青、光学棱镜、唯美落樱 🌸，还会同步把全套 13 种系统指针一起换装；暂停或退出时自动无损还原，完全不用担心改乱系统。
* 🎛️ **自由叠 Buff、随便调颜色**：点一下右下角托盘图标就能呼出控制面板——丝滑流体拖尾、V 形水面波纹 🌊、手电筒透光黑色蒙版 🔦（自动避开任务栏）、录屏演示模式随便叠，配色也能自己取 🎨！
* 🛡️ **日常超省心**：自带防手滑双开保护、全屏打游戏/看视频自动隐身避让 🎮，还会乖乖记住你的所有设置，支持开机自启。

### 🚀 快速开玩

* **懒人直装版**：懒得配环境？直接前往本仓库右侧 **Releases** 附件下载打包好的 `MouseFX.exe`，双击就能玩 🎉！
* **源码运行版**（Windows 10 / 11，Python 3.10+）：

```bash
# 1. 装个 PyQt6 就够了
pip install PyQt6

# 2. 直接跑起来
python windows_mouse_fx.py
```

* **自己动手打包 `.exe`**：

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name MouseFX windows_mouse_fx.py
```

运行后左键点一下右下角系统托盘图标即可打开控制面板～ 🖱️✨

> ⚠️ 首次运行 Windows 可能提示「已保护你的电脑」，点「更多信息」→「仍要运行」。

### 🆘 指针卡住了？

被强杀后指针可能没还原，任选：

* 重新打开 MouseFX 🧹
* 运行 `MouseFX.exe --restore` ⚡
* 或者注销、重启

---

## 📄 License

MIT — see [LICENSE](LICENSE). Fork it, ship it, sell it; just keep the copyright notice. 🍀
