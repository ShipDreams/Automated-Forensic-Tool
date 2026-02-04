# 测试说明

## 运行测试

```bash
cd /Users/apple/Automated-Forensic-Tool-1

# 运行所有测试
python3 -m pytest tests/ -v

# 或者使用 unittest
python3 -m unittest discover tests/ -v

# 运行单个测试文件
python3 tests/test_basic.py
```

## 测试覆盖的模块

1. **PlatformRouter** - URL 平台识别
2. **Task/TaskModel** - 任务模型和生命周期
3. **RiskDetector** - 风险检测关键词
4. **HumanSimulator** - 人类行为模拟
5. **StateDetector** - 页面状态检测
6. **CooldownManager** - 冷却管理

## 注意事项

- 这些测试不需要连接 Android 设备
- 测试使用临时文件，不会影响实际配置
- 运行前请先执行清理脚本：`bash scripts/cleanup.sh`
