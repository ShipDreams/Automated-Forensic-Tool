#!/usr/bin/env python3
"""
Android 自动取证主流程
支持多平台的通用取证框架
"""

import sys
import time
import logging
import argparse
from pathlib import Path

# 确保 logs 目录存在
log_dir = Path(__file__).parent.parent / 'logs'
log_dir.mkdir(exist_ok=True)

# 导入自定义模块
try:
    from core.adb_controller import ADBController
    from core.recorder import ScreenRecorder
    from core.ui_locator import UILocator
    from platforms import PlatformRouter
    from antibot import AntiBot, TaobaoAntiBot
    from task import TaskManager, Task, TaskResult
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("尝试使用兼容模式...")
    # 兼容旧方式
    from adb_controller import ADBController
    from recorder import ScreenRecorder
    from ui_locator import UILocator
    PlatformRouter = None
    AntiBot = None
    TaobaoAntiBot = None
    TaskManager = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'evidence.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class EvidenceCollector:
    """
    取证流程管理器

    负责公共流程（环境检查、录屏、时间锚点），
    平台特定流程委托给 PlatformHandler 处理。
    """

    def __init__(self, device_id: str = None, enable_antibot: bool = True):
        """
        初始化取证管理器

        Args:
            device_id: 设备 ID（可选）
            enable_antibot: 是否启用防风控功能
        """
        self.adb = ADBController(device_id)
        self.recorder = ScreenRecorder(self.adb)
        self.locator = UILocator(self.adb)

        # AntiBot 防风控
        self.antibot = None
        if enable_antibot and AntiBot:
            try:
                self.antibot = AntiBot()
                logger.info("✓ AntiBot 防风控模块已启用")
            except Exception as e:
                logger.warning(f"AntiBot 初始化失败: {e}")

        # 平台路由器
        if PlatformRouter:
            self.router = PlatformRouter(self.adb, self.locator, self.antibot)
        else:
            self.router = None

    # ==================== 公共流程 ====================

    def stage_1_check_environment(self) -> bool:
        """阶段 1: 环境检查与连接验证"""
        logger.info("=" * 60)
        logger.info("阶段 1: 环境检查与连接验证")
        logger.info("=" * 60)

        if not self.adb.device_id:
            logger.error("✗ 未检测到设备，请连接设备后重试")
            return False
        logger.info(f"✓ 设备已连接: {self.adb.device_id}")

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            logger.error("✗ 无法获取屏幕分辨率")
            return False
        logger.info(f"✓ 屏幕分辨率: {screen_size[0]}x{screen_size[1]}")

        if not self.adb.check_connection():
            logger.error("✗ 设备连接异常")
            return False
        logger.info("✓ 设备连接正常")

        self.adb.wake_screen()
        logger.info("✓ 屏幕已唤醒")

        # 检查冷却状态
        if self.antibot and not self.antibot.can_proceed():
            status = self.antibot.get_cooldown_status()
            remaining = status.get('remaining_seconds', 0)
            logger.warning(f"⚠ 当前处于冷却期，剩余 {int(remaining)} 秒")
            logger.info("可使用 --no-antibot 参数跳过冷却检查")
            return False

        return True

    def stage_2_start_recording(self) -> bool:
        """阶段 2: 启动实时保App录屏"""
        logger.info("=" * 60)
        logger.info("阶段 2: 启动实时保App录屏")
        logger.info("=" * 60)

        logger.info("启用触摸可视化...")
        self.adb.enable_visual_feedback()
        time.sleep(1)

        if not self.recorder.start_recording():
            logger.error("✗ 启动实时保录屏失败")
            return False

        logger.info("✓ 实时保录屏已启动")
        return True

    def stage_3_show_beijing_time(self) -> bool:
        """阶段 3: 打开北京时间作为时间锚点"""
        logger.info("=" * 60)
        logger.info("阶段 3: 打开北京时间作为时间锚点")
        logger.info("=" * 60)

        try:
            url = "https://www.beijing-time.org/"
            logger.info(f"打开北京时间: {url}")

            if not self.adb.open_url(url):
                logger.error("✗ 无法打开北京时间网站")
                return False

            logger.info("等待5秒让页面加载...")
            time.sleep(5)

            logger.info("停留5秒展示北京时间...")
            time.sleep(5)

            logger.info("✓ 北京时间展示完成")
            return True

        except Exception as e:
            logger.error(f"展示北京时间失败: {e}")
            return False

    def stage_9_export_evidence(self) -> bool:
        """阶段 9: 停止实时保录屏并保存"""
        logger.info("=" * 60)
        logger.info("阶段 9: 停止实时保录屏并保存")
        logger.info("=" * 60)

        if not self.recorder.stop_recording():
            logger.error("✗ 停止实时保录屏失败")
            return False

        logger.info("✓ 实时保录屏已停止并保存")
        self.adb.disable_visual_feedback()

        # 记录任务完成
        if self.antibot:
            self.antibot.record_task_done(success=True)

        return True

    # ==================== 主流程 ====================

    def run_full_process(
        self,
        product_url: str,
        video_play_duration: int = 30
    ) -> bool:
        """
        执行完整取证流程

        Args:
            product_url: 商品链接（支持淘宝/天猫/京东/抖音等）
            video_play_duration: 视频录制时长（秒）

        Returns:
            是否成功完成取证
        """
        logger.info("*" * 60)
        logger.info("开始执行 Android 自动取证流程")
        logger.info(f"商品链接: {product_url}")
        logger.info("*" * 60)

        recording_started = False  # 标记录屏是否已启动

        try:
            # 阶段 1: 环境检查
            if not self.stage_1_check_environment():
                logger.error("环境检查失败，终止流程")
                return False

            # 阶段 2: 启动实时保录屏
            if not self.stage_2_start_recording():
                logger.error("启动实时保录屏失败，终止流程")
                return False
            recording_started = True

            # 阶段 3: 展示北京时间
            if not self.stage_3_show_beijing_time():
                logger.error("展示北京时间失败，终止流程")
                self._cleanup_on_failure(recording_started)
                return False

            # 阶段 4-8: 平台特定流程
            if self.router:
                # 使用平台路由器
                try:
                    handler = self.router.get_handler(product_url)
                    logger.info(f"使用 {handler.get_platform_display_name()} 平台处理器")

                    if not handler.execute(product_url, video_play_duration):
                        logger.error("平台取证流程失败")
                        if self.antibot:
                            self.antibot.record_task_done(success=False)
                        self._cleanup_on_failure(recording_started)
                        return False

                except NotImplementedError as e:
                    logger.error(f"平台未实现: {e}")
                    self._cleanup_on_failure(recording_started)
                    return False

                except ValueError as e:
                    logger.error(f"无法识别平台: {e}")
                    self._cleanup_on_failure(recording_started)
                    return False
            else:
                # 兼容模式：直接使用旧的淘宝流程
                logger.warning("平台路由器不可用，使用兼容模式")
                if not self._run_legacy_taobao_process(product_url, video_play_duration):
                    self._cleanup_on_failure(recording_started)
                    return False

            # 阶段 9: 停止并导出（成功时保存）
            if not self.stage_9_export_evidence():
                logger.error("导出取证文件失败")
                return False

            logger.info("*" * 60)
            logger.info("✓ 取证流程全部完成")
            logger.info("*" * 60)
            return True

        except KeyboardInterrupt:
            logger.warning("用户中断，尝试保存录屏...")
            self.recorder.stop_recording()
            return False

        except Exception as e:
            logger.error(f"取证流程异常: {e}", exc_info=True)
            if self.antibot:
                self.antibot.record_task_done(success=False)
            self._cleanup_on_failure(recording_started)
            return False

    def _cleanup_on_failure(self, recording_started: bool):
        """
        任务失败时清理录屏状态

        Args:
            recording_started: 录屏是否已启动
        """
        if recording_started:
            logger.info("任务失败，取消录屏（不保存）...")
            try:
                self.recorder.cancel_recording()
            except Exception as e:
                logger.error(f"取消录屏失败: {e}")

    def _run_legacy_taobao_process(
        self,
        product_url: str,
        video_play_duration: int
    ) -> bool:
        """
        兼容模式：旧的淘宝流程（当 PlatformRouter 不可用时）

        这是从原 main.py 保留的逻辑，用于向后兼容。
        新代码应该使用 PlatformRouter。
        """
        logger.warning("使用旧版淘宝流程（兼容模式）")

        # 阶段 4: 打开应用商店
        if not self.adb.open_app_store_and_search_taobao():
            logger.error("打开应用商店失败")
            return False
        time.sleep(6)

        # 阶段 5: 从应用商店打开淘宝
        if not self.locator.find_and_click_app_store_open_button(max_attempts=3):
            logger.error("未能点击'打开'按钮")
            return False
        time.sleep(10)

        # 阶段 6: 在淘宝中打开商品
        time.sleep(3)
        self.adb.press_back()
        time.sleep(1)

        root = self.locator.dump_and_parse()
        if not root:
            logger.error("无法获取 UI 层级")
            return False

        search_box = self.locator.find_taobao_search_box(root)
        if not search_box:
            logger.error("未找到淘宝搜索框")
            return False

        if not self.locator.click_element(search_box):
            logger.error("点击搜索框失败")
            return False
        time.sleep(1)

        if not self.adb.input_text(product_url):
            logger.error("输入商品链接失败")
            return False
        time.sleep(1)

        self.adb.press_enter()
        time.sleep(8)

        # 阶段 7: 播放视频
        self.locator.find_and_click_video(max_attempts=3)
        time.sleep(3)

        # 阶段 8: 持续录制
        time.sleep(video_play_duration)

        # 阶段 8.5: 查看店铺资质（简化版）
        root = self.locator.dump_and_parse()
        if root:
            shop_btn = self.locator.find_shop_button(root)
            if shop_btn:
                self.locator.click_element(shop_btn)
                time.sleep(3)

        return True


def _load_taobao_antibot_config() -> dict:
    """加载淘宝防封控配置"""
    config_path = Path(__file__).parent.parent / 'config' / 'antibot.json'
    if config_path.exists():
        try:
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('taobao', {})
        except Exception as e:
            logger.warning(f"加载淘宝防封控配置失败: {e}")
    return {}


def run_batch_mode(task_file: str, device_id: str = None, video_duration: int = 30, enable_antibot: bool = True):
    """
    批量模式：从文件加载任务并依次执行

    支持淘宝专用防封控策略：
    - 每 3-5 个任务执行人类浏览模拟
    - 每 3-5 个周期进入 15 分钟冷却期

    Args:
        task_file: 任务文件路径（JSON/CSV/TXT）
        device_id: 设备 ID
        video_duration: 视频录制时长
        enable_antibot: 是否启用防封控
    """
    if not TaskManager:
        logger.error("TaskManager 模块不可用，无法使用批量模式")
        return False

    logger.info("=" * 60)
    logger.info("批量取证模式")
    logger.info(f"任务文件: {task_file}")
    logger.info("=" * 60)

    # 初始化
    collector = EvidenceCollector(device_id=device_id, enable_antibot=enable_antibot)
    task_manager = TaskManager()

    # 初始化淘宝防封控（如果启用）
    taobao_antibot = None
    if enable_antibot and TaobaoAntiBot:
        try:
            taobao_config = _load_taobao_antibot_config()
            taobao_antibot = TaobaoAntiBot(
                adb_controller=collector.adb,
                ui_locator=collector.locator,
                config=taobao_config,
                device_id=collector.adb.device_id
            )
            logger.info("✓ 淘宝防封控模块已启用")
            status = taobao_antibot.get_status()
            logger.info(f"  当前状态: 周期内任务 {status['tasks_in_cycle']}/{status['tasks_per_cycle_target']}, "
                       f"已完成周期 {status['completed_cycles']}/{status['cycles_before_cooldown_target']}")

            # 检查是否在冷却期
            if taobao_antibot.is_cooling_down():
                remaining = taobao_antibot.get_remaining_cooldown()
                logger.warning(f"⚠ 当前设备处于冷却期，剩余 {int(remaining.total_seconds())} 秒")
                logger.info("等待冷却期结束...")
                time.sleep(remaining.total_seconds())
                logger.info("✓ 冷却期已结束，继续执行")

        except Exception as e:
            logger.warning(f"淘宝防封控初始化失败: {e}")
            taobao_antibot = None

    # 加载任务
    count = task_manager.load_tasks_from_file(task_file)
    if count == 0:
        logger.error("未加载到任何任务")
        return False

    logger.info(f"加载了 {count} 个任务")

    # 设置执行器
    def execute_task(task: Task) -> TaskResult:
        """任务执行函数"""
        logger.info(f"执行任务: {task.id} - {task.product_url[:50]}...")

        # 检查冷却状态
        if taobao_antibot and taobao_antibot.is_cooling_down():
            remaining = taobao_antibot.get_remaining_cooldown()
            logger.warning(f"当前处于冷却期，剩余 {int(remaining.total_seconds())} 秒")
            logger.info("等待冷却期结束...")
            time.sleep(remaining.total_seconds())
            logger.info("✓ 冷却期已结束")

        success = collector.run_full_process(
            product_url=task.product_url,
            video_play_duration=task.video_duration or video_duration
        )

        # 记录任务完成并检查是否需要防封控动作（无论成功失败都计数）
        try:
            if taobao_antibot:
                # 检测是否是淘宝链接
                is_taobao = 'taobao' in task.product_url.lower() or 'tmall' in task.product_url.lower() or 'tb.cn' in task.product_url.lower()
                logger.info(f"防封控检查: is_taobao={is_taobao}, url={task.product_url[:50]}")
                if is_taobao:
                    should_browse, should_cooldown = taobao_antibot.record_task_complete()
                    status = taobao_antibot.get_status()
                    logger.info(f"防封控状态: 周期内任务={status['tasks_in_cycle']}/{status['tasks_per_cycle_target']}, "
                               f"已完成周期={status['completed_cycles']}/{status['cycles_before_cooldown_target']}, "
                               f"should_browse={should_browse}, should_cooldown={should_cooldown}")

                    if should_browse:
                        logger.info("=" * 60)
                        logger.info("触发周期结束动作：模拟人类浏览")
                        logger.info("=" * 60)
                        taobao_antibot.execute_cycle_end_actions()

                    if should_cooldown:
                        taobao_antibot.trigger_cooldown("完成多个周期")
                        # 关闭淘宝进程
                        taobao_antibot.close_taobao()
            else:
                logger.warning("防封控未启用: taobao_antibot 为 None")
        except Exception as e:
            logger.error(f"防封控处理异常: {e}", exc_info=True)

        # 每个任务结束后关闭两个App，保证下次任务初始状态
        logger.info("关闭淘宝和实时保进程，确保下次任务初始状态...")
        collector.adb.force_stop_app("com.taobao.taobao")
        collector.adb.force_stop_app("com.a1010bao.web.rdbao")

        return TaskResult(
            success=success,
            message="取证完成" if success else "取证失败"
        )

    task_manager.set_executor(execute_task)

    # 执行所有任务
    stats = task_manager.run_all(delay_between_tasks=10)

    # 任务全部完成后关闭淘宝
    if taobao_antibot:
        logger.info("所有任务完成，关闭淘宝进程")
        taobao_antibot.close_taobao()

    return stats['failed'] == 0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Android 自动取证工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单链接取证
  python main.py "https://item.taobao.com/item.htm?id=xxx"

  # 批量取证
  python main.py --batch tasks.json

  # 禁用防风控（跳过冷却检查）
  python main.py --no-antibot "https://item.taobao.com/item.htm?id=xxx"
        """
    )

    # 互斥组：单链接模式 vs 批量模式
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        'product_url',
        nargs='?',
        help='商品链接（支持淘宝/天猫/京东/抖音等）'
    )
    mode_group.add_argument(
        '--batch', '-b',
        metavar='FILE',
        help='批量模式：从文件加载任务（支持 JSON/CSV/TXT）'
    )

    parser.add_argument(
        '-d', '--device',
        help='设备 ID（可选，默认自动检测）',
        default=None
    )
    parser.add_argument(
        '-p', '--play-duration',
        help='视频播放录制时长（秒），默认 30',
        type=int,
        default=30
    )
    parser.add_argument(
        '--no-antibot',
        action='store_true',
        help='禁用防风控功能（跳过冷却检查和人类行为模拟）'
    )

    args = parser.parse_args()

    # 批量模式
    if args.batch:
        success = run_batch_mode(
            task_file=args.batch,
            device_id=args.device,
            video_duration=args.play_duration,
            enable_antibot=not args.no_antibot
        )
        sys.exit(0 if success else 1)

    # 单链接模式
    collector = EvidenceCollector(
        device_id=args.device,
        enable_antibot=not args.no_antibot
    )

    success = collector.run_full_process(
        product_url=args.product_url,
        video_play_duration=args.play_duration
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
