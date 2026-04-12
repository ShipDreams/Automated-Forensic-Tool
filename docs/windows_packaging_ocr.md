# Windows 打包与 OCR 验证说明

## 推荐环境

- Python 3.10.11
- paddleocr 3.3.0
- paddlepaddle 3.2.0

说明：
- 该组合已在 Windows 打包机源码环境中验证通过最小 OCR 单测。
- 旧组合 `paddleocr==3.4.0` + `paddlepaddle==3.3.1` 在 Windows 上出现 OCR 运行时异常。

## 一次性准备

在项目根目录执行：

```bat
py -3.10 -m venv .venv310_build
.venv310_build\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

确认版本：

```bat
python -c "import paddleocr, paddle, sys; print(sys.version); print('paddleocr=', getattr(paddleocr,'__version__','unknown')); print('paddle=', getattr(paddle,'__version__','unknown'))"
```

## OCR 最小单测

将测试截图放到 `docs\ocr_test.png`，然后执行：

```bat
python -c "import sys; sys.path.insert(0, r'src'); from core.ocr_engine import extract_company_name_with_status; print(extract_company_name_with_status(r'docs\ocr_test.png'))"
```

预期结果：

- 成功时输出形如：

```txt
('某某有限公司', None)
```

- 如果返回 `OCR异常: ...`，不要继续打包，先处理 OCR 环境问题。

## 源码完整流程验证

使用文件任务模式，不依赖 MySQL。

```bat
python src\main.py --batch docs\tasks.csv --grouped -d 设备ID --no-antibot
```

建议至少验证：

1. 能完成完整取证流程
2. 资质页截图成功
3. OCR 后处理正常

## 打包

仍在同一个虚拟环境里执行：

```bat
python build\build_windows.py
```

注意：
- 打包脚本使用当前解释器环境，即 `sys.executable -m PyInstaller`
- 因此必须在通过验证的 Python 3.10 环境中执行打包

## exe 验证

打开：

```txt
dist\ForensicTool\ForensicTool.exe
```

GUI 中按以下方式测试：

1. 任务来源选择“文件”
2. 选择 `docs\tasks.csv`
3. 选择 grouped 模式
4. 选择和源码测试相同的设备
5. 启动任务并观察日志

## 结果判断

1. 源码通过，exe 通过
   说明当前 Windows 打包环境可发布

2. 源码通过，exe 失败
   优先检查 PyInstaller 打包收包问题

3. 源码失败
   不要继续打包，先修复 OCR 运行环境

## 关于 OCR 速度

- Windows 旧款低压 CPU 设备上，OCR 速度可能明显慢于 macOS
- 只要最小单测和完整流程能稳定通过，说明功能正确
- 若要优化性能，应在稳定版本基础上再做轻量化改造
