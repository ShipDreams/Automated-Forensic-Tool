# Android 自动取证工具

通过 ADB 控制 Android 设备，配合"实时保"App 自动完成电商平台商品取证录屏。

## 系统要求

- Python 3.8+
- ADB (Android Debug Bridge)
- Android 设备（无需 root）
- 实时保 App（已安装并授权）
- 淘宝/天猫 App（已安装并登录）

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

**Windows:**
1. 下载 [Android SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. 解压到任意目录（如 `C:\platform-tools`）
3. 将该目录添加到系统环境变量 PATH 中
4. 打开命令提示符，运行 `adb version` 验证安装

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 设备准备

1. 开启 USB 调试：设置 → 开发者选项 → USB 调试
2. 连接设备并授权 ADB 调试
3. 确保淘宝和实时保 App 已安装

### 4. 设备优化设置（推荐）

在**开发者选项**中进行以下设置可显著提升执行速度和稳定性：

| 设置项 | 推荐值 | 说明 |
|--------|--------|------|
| 窗口动画缩放 | 关闭 或 0.5x | 减少动画等待时间 |
| 过渡动画缩放 | 关闭 或 0.5x | 减少页面切换延迟 |
| Animator 时长缩放 | 关闭 或 0.5x | 加快控件动画 |
| 强制进行 GPU 渲染 | 开启 | 提升界面响应速度 |
| MIUI 优化（小米设备） | 关闭 | 提升 UI dump 稳定性 |

## 使用方法

### 单链接取证

```bash
python src/main.py "https://item.taobao.com/item.htm?id=xxxxx"
```

### 批量取证（单设备）

```bash
python src/main.py --batch tasks.csv
```

### 批量取证（多设备并行）

```bash
python src/main.py --batch tasks.csv --parallel
```

指定设备：
```bash
python src/main.py --batch tasks.csv --parallel --devices "device1,device2"
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `product_url` | 商品链接（单链接模式） |
| `-b, --batch FILE` | 批量模式，从文件加载任务 |
| `-d, --device ID` | 指定设备 ID |
| `-p, --play-duration N` | 视频录制时长，默认 30 秒 |
| `--parallel` | 启用多设备并行模式 |
| `--devices "id1,id2"` | 指定并行设备列表 |
| `--no-antibot` | 禁用防检测（跳过冷却检查） |
| `--lang zh_CN/en_US` | 设置语言 |

## 任务文件格式

### CSV 格式

```csv
url
https://item.taobao.com/item.htm?id=123456
https://item.taobao.com/item.htm?id=789012
```

### JSON 格式

```json
{
  "tasks": [
    {"url": "https://item.taobao.com/item.htm?id=123456"},
    {"url": "https://item.taobao.com/item.htm?id=789012", "video_duration": 60}
  ]
}
```

## 输出说明

### 录像文件

取证录像保存在**实时保 App** 内，可在 App 中查看和导出。

### 执行报告

批量任务完成后，报告保存在 `reports/` 目录：

```
reports/
└── batch_report_20260206_182955.json
```

报告内容示例：
```json
{
  "summary": {
    "total": 10,
    "completed": 8,
    "failed": 2
  },
  "tasks": [
    {"id": "xxx", "url": "...", "status": "completed"},
    ...
  ]
}
```

### 日志文件

运行日志保存在 `logs/evidence.log`。

## 取证流程

1. 环境检查 - 验证设备连接
2. 启动录屏 - 通过实时保 App 开始录屏
3. 展示时间 - 打开北京时间网站作为时间锚点
4. 应用商店 - 打开应用商店搜索淘宝
5. 启动淘宝 - 从应用商店打开淘宝 App
6. 打开商品 - 在搜索框输入商品链接
7. 播放视频 - 打开声音并播放商品视频
8. 查看资质 - 进入店铺查看资质证照
9. 保存录屏 - 停止并保存取证录屏

## 常见问题

**Q: UI dump 频繁失败**
- 建议关闭开发者选项中的动画和 MIUI 优化
- 录屏期间 dump 可能不稳定，工具会自动重试

**Q: 找不到"打开"按钮**
- 确认淘宝已安装
- 等待搜索结果完全加载

**Q: 实时保录屏启动失败**
- 确认实时保 App 已授予录屏权限
- 手动打开实时保确认可正常使用

**Q: 资质证照查看失败导致取证失败**
- 部分店铺页面结构不同，工具会自动重试
- 如持续失败，请检查店铺是否正常显示

## 合规说明

本工具仅用于合法版权取证，使用者需确保：
- 遵守平台服务条款
- 符合当地法律法规
- 取证内容仅作证据使用
