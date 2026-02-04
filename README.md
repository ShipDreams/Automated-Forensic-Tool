# Android 自动取证工具

通过 ADB 控制 Android 设备，配合"实时保"App 自动完成淘宝商品取证录屏的自动化工具。

## 功能特性

- 使用"实时保"App 进行取证级别的屏幕录制
- 自动展示北京时间作为时间锚点
- 品牌自适应应用商店搜索（支持小米/华为/OPPO/vivo/三星等）
- 自动打开淘宝商品页面并播放视频
- 自动查看店铺资质证照
- 触摸操作可视化反馈

## 取证流程

1. **环境检查** - 验证设备连接和屏幕状态
2. **启动录屏** - 通过实时保App开始录屏
3. **展示时间** - 打开北京时间网站作为时间锚点
4. **应用商店** - 打开应用商店搜索淘宝
5. **启动淘宝** - 从应用商店打开淘宝App
6. **打开商品** - 在淘宝搜索框输入商品链接
7. **播放视频** - 打开声音并播放商品视频
8. **录制内容** - 持续录制视频，查看店铺资质
9. **保存录屏** - 停止并保存取证录屏

## 系统要求

- Python 3.8+
- ADB (Android Debug Bridge)
- Android 设备（无需 root）
- 实时保 App（已安装在设备上）
- 淘宝 App（已安装并登录）

## 安装

### 1. 安装 ADB

**Mac:**
```bash
brew install --cask android-platform-tools
```

**Linux:**
```bash
sudo apt-get install android-tools-adb
```

### 2. 准备设备

1. 开启 USB 调试（设置 → 开发者选项 → USB 调试）
2. 用 USB 连接设备并授权
3. 确保淘宝和实时保App已安装

## 使用方法

```bash
cd src
python3 main.py "https://item.taobao.com/item.htm?id=xxxxx"
```

### 可选参数

```bash
python3 main.py <商品链接> [选项]

选项:
  -d, --device DEVICE_ID     指定设备 ID
  -p, --play-duration SECONDS 视频录制时长（默认 30 秒）
```

## 项目结构

```
android-evidence-mvp/
├── src/
│   ├── main.py              # 主流程
│   ├── adb_controller.py    # ADB 命令封装
│   ├── recorder.py          # 实时保录屏管理
│   └── ui_locator.py        # UI 元素定位
├── config/
│   ├── device.json          # 设备配置
│   └── locator_rules.json   # UI 定位规则
├── output/                  # 输出文件
├── logs/                    # 日志文件
└── requirements.txt
```

## 配置说明

### device.json

```json
{
  "device_id": null,
  "recording_settings": {
    "video_play_duration": 30
  }
}
```

## 常见问题

**Q: 应用商店打开失败**
- 检查应用商店是否已启用
- 程序会自动尝试通用协议

**Q: 找不到"打开"按钮**
- 确认淘宝已安装
- 增加等待时间让搜索结果完全加载

**Q: 实时保录屏启动失败**
- 确认实时保App已安装并授予必要权限
- 手动打开实时保App确认可正常使用

## 合规说明

本工具仅用于合法版权取证，使用者需确保：
- 遵守平台服务条款
- 符合当地法律法规
- 取证内容仅作证据使用
