# Android 自动取证系统 - 架构设计文档

> **版本**: v2.0
> **日期**: 2026-01-31
> **状态**: 设计阶段

---

## 1. 系统概览

### 1.1 目标

将当前 MVP（淘宝单平台）升级为：
- **多平台**：淘宝、阿里巴巴、京东、抖音
- **可调度**：任务队列、失败重试、设备分配
- **防风控**：人类行为模拟、风险检测、自动冷却
- **长期运行**：30-60 分钟持续运行、状态恢复

### 1.2 核心约束

| 约束 | 说明 |
|------|------|
| **UIAutomator 优先** | 所有操作基于 resource-id / text / content-desc，坐标仅作兜底 |
| **不绕过安全机制** | 不破解、不逆向、不 Hook；验证码失败则安全退出 |
| **人类行为模拟** | 随机延迟、随机滚动、无意义浏览，避免触发风控 |

### 1.3 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           控制端 (Python)                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐           │
│  │ TaskManager │────▶│ StateMachine│────▶│  AntiBot    │           │
│  │  任务调度    │     │   状态机     │     │  防风控      │           │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘           │
│         │                   │                   │                   │
│         ▼                   ▼                   ▼                   │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                   PlatformRouter                         │       │
│  │              平台路由 (根据链接判断平台)                    │       │
│  └───────────────────────┬─────────────────────────────────┘       │
│                          │                                          │
│         ┌────────────────┼────────────────┐                        │
│         ▼                ▼                ▼                        │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐                 │
│  │TaobaoHandler│   │  JDHandler │   │DouyinHandler│  ...           │
│  │  淘宝处理器  │   │  京东处理器 │   │ 抖音处理器  │                 │
│  └──────┬─────┘   └──────┬─────┘   └──────┬─────┘                 │
│         │                │                │                        │
│         └────────────────┼────────────────┘                        │
│                          ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                     Core Layer                           │       │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │       │
│  │  │ ADBController│  │  UILocator   │  │ScreenRecorder│   │       │
│  │  │   ADB 控制   │  │  UI 定位     │  │   录屏管理   │   │       │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │       │
│  └─────────────────────────────────────────────────────────┘       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ ADB over USB/WiFi
                                    ▼
                    ┌───────────────────────────────┐
                    │       Android 设备 (无 root)   │
                    │  ┌─────────┐  ┌─────────────┐ │
                    │  │ 实时保App │  │ 淘宝/京东/.. │ │
                    │  └─────────┘  └─────────────┘ │
                    └───────────────────────────────┘
```

---

## 2. 模块职责

### 2.1 任务管理层 (Task Layer)

#### TaskManager

```
职责：
├── 任务队列管理（加载、分发、状态更新）
├── 失败重试（最多 3 次）
├── 设备分配（失败任务可转移）
├── 冷却期管理（设备级别）
└── 任务持久化（断点续传）

任务状态：
  pending → running → success
                   ↘ failed（重试 3 次后）
                   ↘ risk（触发风控）
```

#### Task 数据结构

```python
@dataclass
class Task:
    task_id: str              # 唯一标识
    platform: str             # taobao | alibaba | jd | douyin
    product_url: str          # 商品链接
    status: TaskStatus        # pending | running | success | failed | risk
    attempt_count: int        # 已尝试次数（max=3）
    assigned_device: str      # 分配的设备 ID
    created_at: datetime
    updated_at: datetime
    error_message: str        # 失败原因
    evidence_path: str        # 取证文件路径
```

### 2.2 状态机层 (State Machine Layer)

#### StateMachine

```
职责：
├── 识别当前页面状态
├── 决定下一步操作
├── 处理异常状态（验证码、登录、未知页面）
└── 提供状态转换日志

公共状态（所有平台共享）：
  INIT           → 初始状态
  HOME           → 平台首页
  SEARCH         → 搜索页
  PRODUCT        → 商品详情页
  VIDEO_PLAYING  → 视频播放中
  SHOP_PAGE      → 店铺页面
  QUALIFICATION  → 资质证照页
  CAPTCHA        → 验证码页面（需人工/自动处理）
  LOGIN_REQUIRED → 需要登录
  UNKNOWN        → 未知状态
  COMPLETED      → 任务完成
  ERROR          → 错误状态
```

#### 状态识别策略

```python
class StateDetector:
    """
    状态检测器
    基于 UI 元素特征识别当前页面状态
    """

    def detect(self, ui_root: ET.Element, platform: str) -> PageState:
        # 优先级从高到低检测
        if self._is_captcha(ui_root):
            return PageState.CAPTCHA
        if self._is_login_required(ui_root):
            return PageState.LOGIN_REQUIRED
        if self._is_video_playing(ui_root, platform):
            return PageState.VIDEO_PLAYING
        # ... 其他状态检测
```

### 2.3 防风控层 (AntiBot Layer)

#### AntiBot

```
职责：
├── 人类行为模拟
│   ├── human_sleep(min_ms, max_ms)    # 随机等待
│   ├── human_scroll(direction)         # 随机滚动
│   ├── human_click(element)            # 延迟点击
│   └── random_browse()                 # 无意义浏览
│
├── 风险检测
│   ├── detect_captcha()                # 验证码检测
│   ├── detect_login_page()             # 登录页检测
│   ├── detect_rate_limit()             # 频率限制检测
│   ├── detect_ui_anomaly()             # UI 异常检测
│   └── detect_block_page()             # 封禁页面检测
│
└── 冷却管理
    ├── should_cooldown()               # 是否需要冷却
    ├── enter_cooldown(duration)        # 进入冷却期
    └── get_cooldown_remaining()        # 剩余冷却时间
```

#### RiskDetector

```python
class RiskDetector:
    """
    风险检测器
    检测各种异常情况
    """

    # 风险信号
    RISK_SIGNALS = {
        'captcha_keywords': ['验证码', '滑动验证', '安全验证', 'captcha'],
        'login_keywords': ['登录', '请登录', '登录后查看', 'login'],
        'rate_limit_keywords': ['操作频繁', '请稍后再试', '访问过于频繁'],
        'block_keywords': ['账号异常', '暂时无法访问', '违规'],
    }

    # UI 异常检测
    def detect_ui_anomaly(self, ui_root) -> bool:
        """
        检测 UI dump 是否异常
        - 节点数过少（<10）
        - dump 失败
        - 页面空白
        """
```

### 2.4 平台路由层 (Platform Router Layer)

#### PlatformRouter

```
职责：
├── 根据商品链接识别平台
├── 路由到对应的 Handler
└── 统一错误处理

链接识别规则：
  taobao.com / tmall.com / tb.cn        → TaobaoHandler
  1688.com / alibaba.com                → AlibabaHandler
  jd.com / m.jd.com                     → JDHandler
  douyin.com / v.douyin.com             → DouyinHandler
```

### 2.5 平台处理器层 (Platform Handler Layer)

#### BasePlatformHandler (抽象基类)

```python
class BasePlatformHandler(ABC):
    """
    平台处理器基类
    定义取证流程的标准接口
    """

    @abstractmethod
    def get_platform_name(self) -> str:
        """返回平台名称"""

    @abstractmethod
    def get_state_mapping(self) -> Dict[str, StateDetectionRule]:
        """返回平台特定的状态检测规则"""

    @abstractmethod
    def open_product(self, url: str) -> bool:
        """打开商品页"""

    @abstractmethod
    def play_video(self) -> bool:
        """播放商品视频"""

    @abstractmethod
    def view_shop_qualification(self) -> bool:
        """查看店铺资质"""
```

#### TaobaoHandler (保留现有逻辑)

```python
class TaobaoHandler(BasePlatformHandler):
    """
    淘宝平台处理器
    继承自 MVP 的实现，增加状态机集成
    """

    # 复用现有的 UI 定位逻辑
    # 集成 AntiBot 行为
    # 支持状态机驱动
```

### 2.6 核心层 (Core Layer) - 保留现有实现

| 模块 | 职责 | 改动 |
|------|------|------|
| `ADBController` | ADB 命令封装 | **扩展**：增加 AntiBot 集成点 |
| `UILocator` | UI 元素定位 | **扩展**：增加状态检测方法 |
| `ScreenRecorder` | 实时保录屏管理 | **保留**：无需修改 |

---

## 3. 数据流

### 3.1 任务执行流

```
┌──────────┐    ┌───────────┐    ┌────────────┐    ┌──────────────┐
│ 任务队列  │───▶│TaskManager│───▶│StateMachine│───▶│PlatformHandler│
│ (CSV/JSON)│    │  分发任务  │    │  状态驱动   │    │   执行操作    │
└──────────┘    └───────────┘    └────────────┘    └──────────────┘
                     │                 │                    │
                     │                 │                    ▼
                     │                 │           ┌──────────────┐
                     │                 │           │   AntiBot    │
                     │                 │           │  行为模拟    │
                     │                 │           └──────────────┘
                     │                 │                    │
                     │                 ▼                    ▼
                     │          ┌────────────┐     ┌──────────────┐
                     │          │RiskDetector│     │  UILocator   │
                     │          │ 风险检测   │     │  元素定位    │
                     │          └────────────┘     └──────────────┘
                     │                 │                    │
                     ▼                 ▼                    ▼
              ┌─────────────────────────────────────────────────┐
              │                  ADBController                   │
              │                  设备控制层                       │
              └─────────────────────────────────────────────────┘
```

### 3.2 状态转换流（以淘宝为例）

```
INIT
  │
  ▼ (启动录屏)
RECORDING_STARTED
  │
  ▼ (打开北京时间)
TIME_ANCHOR_SHOWN
  │
  ▼ (打开应用商店)
APP_STORE_SEARCH
  │
  ▼ (点击"打开")
HOME
  │
  ▼ (输入商品链接)
SEARCH
  │
  ▼ (页面加载)
PRODUCT
  │
  ├─▶ CAPTCHA (检测到验证码) ─▶ 处理/退出
  │
  ▼ (点击视频)
VIDEO_PLAYING
  │
  ▼ (点击店铺)
SHOP_PAGE
  │
  ▼ (查看资质)
QUALIFICATION
  │
  ▼ (停止录屏)
COMPLETED
```

---

## 4. 目录结构

### 4.1 目录结构

```
android-evidence-mvp/
├── src/
│   ├── core/                      # 核心层（保留+扩展）
│   │   ├── __init__.py
│   │   ├── adb_controller.py      # [保留] ADB 控制
│   │   ├── ui_locator.py          # [保留] UI 定位
│   │   └── recorder.py            # [保留] 录屏管理
│   │
│   ├── task/                      # 任务管理层（新增）
│   │   ├── __init__.py
│   │   ├── task_manager.py        # 任务调度
│   │   ├── task_model.py          # 任务数据模型
│   │   └── task_loader.py         # 任务加载器（CSV/JSON）
│   │
│   ├── state/                     # 状态机层（新增）
│   │   ├── __init__.py
│   │   ├── state_machine.py       # 状态机核心
│   │   ├── state_detector.py      # 状态检测器
│   │   └── states.py              # 状态定义
│   │
│   ├── antibot/                   # 防风控层（新增）
│   │   ├── __init__.py
│   │   ├── antibot.py             # 人类行为模拟
│   │   ├── risk_detector.py       # 风险检测
│   │   └── cooldown.py            # 冷却管理
│   │
│   ├── platform/                  # 平台处理器层（新增）
│   │   ├── __init__.py
│   │   ├── router.py              # 平台路由
│   │   ├── base_handler.py        # 处理器基类
│   │   ├── taobao_handler.py      # 淘宝处理器（重构自 main.py）
│   │   ├── alibaba_handler.py     # 阿里巴巴处理器
│   │   ├── jd_handler.py          # 京东处理器
│   │   └── douyin_handler.py      # 抖音处理器
│   │
│   ├── main.py                    # [重构] 入口，集成新架构
│   └── cli.py                     # 命令行接口
│
├── config/
│   ├── device.json                # [保留] 设备配置
│   ├── locator_rules.json         # [保留] UI 定位规则
│   ├── platform_rules/            # 新增：各平台配置
│   │   ├── taobao.json
│   │   ├── alibaba.json
│   │   ├── jd.json
│   │   └── douyin.json
│   └── antibot.json               # 新增：防风控配置
│
├── tasks/                         # 新增：任务文件目录
│   ├── pending/                   # 待处理任务
│   ├── completed/                 # 已完成任务
│   └── failed/                    # 失败任务
│
├── logs/
│   └── evidence.log
│
├── output/                        # 取证输出
│
├── docs/
│   └── ARCHITECTURE.md            # 本文档
│
├── requirements.txt
└── README.md
```

### 4.2 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/adb_controller.py` | **移动** | → `src/core/adb_controller.py` |
| `src/ui_locator.py` | **移动** | → `src/core/ui_locator.py` |
| `src/recorder.py` | **移动** | → `src/core/recorder.py` |
| `src/main.py` | **重构** | 提取淘宝逻辑到 `platform/taobao_handler.py` |
| `src/task/*` | **新增** | 任务管理模块 |
| `src/state/*` | **新增** | 状态机模块 |
| `src/antibot/*` | **新增** | 防风控模块 |
| `src/platform/*` | **新增** | 平台处理器模块 |
| `config/antibot.json` | **新增** | 防风控配置 |
| `config/platform_rules/*` | **新增** | 各平台 UI 规则 |

---

## 5. 配置文件设计

### 5.1 antibot.json

```json
{
  "human_behavior": {
    "sleep": {
      "min_ms": 500,
      "max_ms": 2000,
      "after_click_min_ms": 800,
      "after_click_max_ms": 1500
    },
    "scroll": {
      "min_distance": 200,
      "max_distance": 600,
      "min_duration_ms": 300,
      "max_duration_ms": 800
    },
    "random_browse": {
      "enabled": true,
      "probability": 0.1,
      "actions": ["scroll_up", "scroll_down", "wait"]
    }
  },
  "risk_detection": {
    "captcha_keywords": ["验证码", "滑动验证", "安全验证", "captcha", "verify"],
    "login_keywords": ["登录", "请登录", "登录后", "login", "sign in"],
    "rate_limit_keywords": ["操作频繁", "请稍后", "访问过于频繁"],
    "block_keywords": ["账号异常", "暂时无法访问", "违规"],
    "ui_anomaly": {
      "min_node_count": 10,
      "empty_page_threshold": 5
    }
  },
  "cooldown": {
    "enabled": true,
    "trigger_on_risk": true,
    "duration_minutes": 15,
    "max_continuous_tasks": 10
  }
}
```

### 5.2 任务文件格式 (tasks.csv)

```csv
task_id,platform,product_url,priority,notes
T001,taobao,https://item.taobao.com/item.htm?id=123456,high,测试商品1
T002,jd,https://item.jd.com/100001,normal,京东商品
T003,douyin,https://v.douyin.com/abc123,low,抖音商品
```

---

## 6. 实施路线图

### 第一阶段：基础重构（1-2 天）
1. 创建目录结构
2. 移动现有核心模块到 `src/core/`
3. 确保移动后 MVP 流程仍可运行

### 第二阶段：AntiBot 模块（2-3 天）
1. 实现 `human_sleep`, `human_scroll`, `human_click`
2. 实现 `RiskDetector`
3. 集成到现有 ADB 操作中

### 第三阶段：TaskManager 模块（2-3 天）
1. 实现任务加载（CSV/JSON）
2. 实现任务状态管理
3. 实现失败重试逻辑

### 第四阶段：StateMachine 模块（3-4 天）
1. 定义状态枚举
2. 实现 `StateDetector`
3. 重构淘宝流程为状态机驱动

### 第五阶段：多平台支持（每平台 2-3 天）
1. 抽象 `BasePlatformHandler`
2. 提取 `TaobaoHandler`
3. 依次实现：阿里巴巴 → 京东 → 抖音

---

## 7. 关键接口定义

### 7.1 TaskManager

```python
class TaskManager:
    def load_tasks(self, file_path: str) -> List[Task]:
        """从文件加载任务"""

    def get_next_task(self, device_id: str) -> Optional[Task]:
        """获取下一个待执行任务"""

    def update_task_status(self, task_id: str, status: TaskStatus, error: str = None):
        """更新任务状态"""

    def reassign_failed_task(self, task_id: str, new_device: str) -> bool:
        """将失败任务分配给其他设备"""
```

### 7.2 StateMachine

```python
class StateMachine:
    def detect_current_state(self) -> PageState:
        """检测当前页面状态"""

    def get_expected_states(self) -> List[PageState]:
        """获取当前步骤允许的状态集合"""

    def transition(self, action: Action) -> PageState:
        """执行动作并返回新状态"""

    def is_terminal_state(self, state: PageState) -> bool:
        """判断是否为终止状态"""
```

### 7.3 AntiBot

```python
class AntiBot:
    def human_sleep(self, min_ms: int = 500, max_ms: int = 2000):
        """人类模式等待"""

    def human_click(self, element: UIElement) -> bool:
        """人类模式点击（带随机延迟）"""

    def human_scroll(self, direction: str = 'down', distance: int = None):
        """人类模式滚动"""

    def random_browse(self) -> bool:
        """随机无意义浏览（降低风控）"""

    def check_risk(self, ui_root: ET.Element) -> RiskLevel:
        """检查当前页面风险等级"""
```

### 7.4 BasePlatformHandler

```python
class BasePlatformHandler(ABC):
    @abstractmethod
    def get_platform_name(self) -> str: ...

    @abstractmethod
    def get_app_package(self) -> str: ...

    @abstractmethod
    def open_app_from_store(self) -> bool: ...

    @abstractmethod
    def navigate_to_product(self, url: str) -> bool: ...

    @abstractmethod
    def play_video(self) -> bool: ...

    @abstractmethod
    def view_shop_info(self) -> bool: ...

    @abstractmethod
    def view_qualification(self) -> bool: ...
```

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 平台 UI 更新 | 定位失败 | 配置化定位规则 + 多策略降级 |
| 风控升级 | 账号封禁 | 人类行为模拟 + 自动冷却 + 分散设备 |
| 验证码无法识别 | 任务中断 | 优先自动识别，失败则安全退出并标记 |
| ADB 连接不稳定 | 任务失败 | 连接重试 + 断点续传 |

---

**文档版本**: v2.0
**最后更新**: 2026-01-31
