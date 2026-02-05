#!/usr/bin/env python3
"""
淘宝专用防封控模块
实现淘宝平台特定的人类行为模拟和周期管理
"""

import random
import time
import logging
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TaobaoAntiBot:
    """
    淘宝专用防封控管理器

    核心功能：
    - 模拟人类浏览商品行为（2-5分钟）
    - 周期管理（3-5个任务为一周期）
    - 冷却管理（3-5个周期后进入15分钟冷却）
    - 设备状态持久化
    """

    TAOBAO_PACKAGE = "com.taobao.taobao"

    def __init__(self, adb_controller, ui_locator, config: dict = None, device_id: str = None):
        """
        初始化淘宝防封控

        Args:
            adb_controller: ADBController 实例
            ui_locator: UILocator 实例
            config: 配置字典（淘宝专用部分）
            device_id: 设备 ID（用于状态持久化）
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.config = config or {}
        self.device_id = device_id or adb_controller.device_id or "default"

        self._load_config()
        self._load_state()

    def _load_config(self):
        """加载配置参数"""
        # 每周期任务数范围
        tasks_range = self.config.get('tasks_per_cycle', [3, 5])
        self.tasks_per_cycle_min = tasks_range[0] if isinstance(tasks_range, list) else 3
        self.tasks_per_cycle_max = tasks_range[1] if isinstance(tasks_range, list) else 5

        # 冷却前周期数范围
        cycles_range = self.config.get('cycles_before_cooldown', [3, 5])
        self.cycles_before_cooldown_min = cycles_range[0] if isinstance(cycles_range, list) else 3
        self.cycles_before_cooldown_max = cycles_range[1] if isinstance(cycles_range, list) else 5

        # 浏览模拟时长范围（分钟）
        browse_range = self.config.get('browse_duration_minutes', [2, 5])
        self.browse_duration_min = browse_range[0] if isinstance(browse_range, list) else 2
        self.browse_duration_max = browse_range[1] if isinstance(browse_range, list) else 5

        # 冷却时长（分钟）
        self.cooldown_duration_minutes = self.config.get('cooldown_duration_minutes', 15)

        # 点击偏移量
        self.click_offset_max_px = self.config.get('click_offset_max_px', 5)

        # 当前周期的目标任务数（随机决定）
        self._current_cycle_target = random.randint(self.tasks_per_cycle_min, self.tasks_per_cycle_max)
        # 当前冷却期的目标周期数（随机决定）
        self._current_cooldown_target = random.randint(self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)

    def _get_state_file_path(self) -> Path:
        """获取设备专属状态文件路径"""
        state_dir = Path(__file__).parent.parent.parent / 'logs'
        state_dir.mkdir(parents=True, exist_ok=True)
        # 使用设备ID作为文件名后缀
        safe_device_id = self.device_id.replace(':', '_').replace('/', '_')
        return state_dir / f'taobao_antibot_state_{safe_device_id}.json'

    def _load_state(self):
        """加载设备状态"""
        state_file = self._get_state_file_path()

        # 默认状态
        self.tasks_in_cycle = 0  # 当前周期内已完成任务数
        self.completed_cycles = 0  # 已完成周期数
        self.cooldown_until: Optional[datetime] = None  # 冷却结束时间
        self.last_task_time: Optional[datetime] = None  # 最后任务时间

        if not state_file.exists():
            logger.info(f"状态文件不存在，使用默认状态: {state_file}")
            return

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.tasks_in_cycle = data.get('tasks_in_cycle', 0)
            self.completed_cycles = data.get('completed_cycles', 0)

            cooldown_str = data.get('cooldown_until')
            if cooldown_str:
                self.cooldown_until = datetime.fromisoformat(cooldown_str)
                # 检查是否已过期
                if self.cooldown_until < datetime.now():
                    logger.info("冷却期已结束，重置状态")
                    self.cooldown_until = None
                    self.completed_cycles = 0
                    self.tasks_in_cycle = 0

            last_task_str = data.get('last_task_time')
            if last_task_str:
                self.last_task_time = datetime.fromisoformat(last_task_str)

            # 恢复目标值
            self._current_cycle_target = data.get('current_cycle_target',
                random.randint(self.tasks_per_cycle_min, self.tasks_per_cycle_max))
            self._current_cooldown_target = data.get('current_cooldown_target',
                random.randint(self.cycles_before_cooldown_min, self.cycles_before_cooldown_max))

            logger.info(f"加载淘宝防封控状态: 周期内任务={self.tasks_in_cycle}/{self._current_cycle_target}, "
                       f"已完成周期={self.completed_cycles}/{self._current_cooldown_target}, "
                       f"冷却中={self.is_cooling_down()}")

        except Exception as e:
            logger.warning(f"加载状态失败: {e}")

    def _save_state(self):
        """保存设备状态"""
        state_file = self._get_state_file_path()

        try:
            data = {
                'device_id': self.device_id,
                'tasks_in_cycle': self.tasks_in_cycle,
                'completed_cycles': self.completed_cycles,
                'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
                'last_task_time': self.last_task_time.isoformat() if self.last_task_time else None,
                'current_cycle_target': self._current_cycle_target,
                'current_cooldown_target': self._current_cooldown_target,
                'updated_at': datetime.now().isoformat()
            }

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"状态已保存: {state_file}")

        except Exception as e:
            logger.error(f"保存状态失败: {e}")

    # ==================== 状态查询 ====================

    def is_cooling_down(self) -> bool:
        """检查是否在冷却期"""
        if self.cooldown_until is None:
            return False

        if datetime.now() >= self.cooldown_until:
            # 冷却结束
            self.cooldown_until = None
            self.completed_cycles = 0
            self.tasks_in_cycle = 0
            self._current_cooldown_target = random.randint(
                self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)
            self._save_state()
            return False

        return True

    def get_remaining_cooldown(self) -> Optional[timedelta]:
        """获取剩余冷却时间"""
        if not self.is_cooling_down():
            return None
        return self.cooldown_until - datetime.now()

    def can_proceed(self) -> bool:
        """检查是否可以执行任务"""
        return not self.is_cooling_down()

    def get_status(self) -> dict:
        """获取当前状态"""
        remaining = self.get_remaining_cooldown()
        return {
            'device_id': self.device_id,
            'tasks_in_cycle': self.tasks_in_cycle,
            'tasks_per_cycle_target': self._current_cycle_target,
            'completed_cycles': self.completed_cycles,
            'cycles_before_cooldown_target': self._current_cooldown_target,
            'is_cooling_down': self.is_cooling_down(),
            'remaining_seconds': remaining.total_seconds() if remaining else 0,
            'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
        }

    # ==================== 任务周期管理 ====================

    def record_task_complete(self) -> Tuple[bool, bool]:
        """
        记录任务完成

        Returns:
            (should_browse, should_cooldown) 元组
            - should_browse: 是否需要执行人类浏览模拟
            - should_cooldown: 是否需要进入冷却期
        """
        self.tasks_in_cycle += 1
        self.last_task_time = datetime.now()

        should_browse = False
        should_cooldown = False

        # 检查是否完成当前周期
        if self.tasks_in_cycle >= self._current_cycle_target:
            should_browse = True
            self.completed_cycles += 1
            self.tasks_in_cycle = 0
            # 为下一周期生成新的随机目标
            self._current_cycle_target = random.randint(
                self.tasks_per_cycle_min, self.tasks_per_cycle_max)

            logger.info(f"完成第 {self.completed_cycles} 个周期，需要执行人类浏览模拟")

            # 检查是否需要冷却
            if self.completed_cycles >= self._current_cooldown_target:
                should_cooldown = True
                logger.info(f"完成 {self.completed_cycles} 个周期，需要进入冷却期")

        self._save_state()
        return should_browse, should_cooldown

    def trigger_cooldown(self, reason: str = "周期完成"):
        """
        触发冷却期

        Args:
            reason: 触发原因
        """
        self.cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_duration_minutes)
        self.completed_cycles = 0
        self.tasks_in_cycle = 0
        # 为下一冷却期生成新的随机目标
        self._current_cooldown_target = random.randint(
            self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)

        self._save_state()
        logger.warning(f"进入冷却期: {reason}，冷却 {self.cooldown_duration_minutes} 分钟，"
                      f"直到 {self.cooldown_until}")

    def reset_state(self):
        """重置状态"""
        self.tasks_in_cycle = 0
        self.completed_cycles = 0
        self.cooldown_until = None
        self._current_cycle_target = random.randint(
            self.tasks_per_cycle_min, self.tasks_per_cycle_max)
        self._current_cooldown_target = random.randint(
            self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)
        self._save_state()
        logger.info("淘宝防封控状态已重置")

    # ==================== 人类行为模拟 ====================

    def _is_in_taobao(self) -> bool:
        """检查当前是否在淘宝 App 内"""
        current_focus = self.adb.get_current_focus()
        if current_focus and 'taobao' in current_focus.lower():
            return True
        return False

    def _random_sleep(self, min_sec: float, max_sec: float):
        """随机延迟"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        return delay

    def _random_scroll(self, direction: str = 'up') -> bool:
        """
        随机滚动

        Args:
            direction: 方向 ('up', 'down')

        Returns:
            是否成功
        """
        screen_size = self.adb.get_screen_size()
        if not screen_size:
            return False

        width, height = screen_size

        # 计算随机滚动参数
        center_x = width // 2 + random.randint(-width // 6, width // 6)
        distance = random.randint(200, 500)
        duration = random.randint(300, 600)

        if direction == 'up':
            start_y = height * 2 // 3 + random.randint(-50, 50)
            end_y = start_y - distance
        else:
            start_y = height // 3 + random.randint(-50, 50)
            end_y = start_y + distance

        end_x = center_x + random.randint(-20, 20)

        # 确保坐标在屏幕范围内
        end_y = max(0, min(end_y, height - 1))
        end_x = max(0, min(end_x, width - 1))

        return self.adb.swipe(center_x, start_y, end_x, end_y, duration)

    def _find_and_click_random_product(self) -> bool:
        """
        随机点击一个商品链接

        Returns:
            是否成功点击
        """
        root = self.locator.dump_and_parse()
        if not root:
            return False

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            return False

        width, height = screen_size

        # 查找中间区域的可点击元素（排除顶部和底部导航栏）
        clickable_elements = self.locator.find_clickable_in_region(
            root, 0, height // 6, width, height * 5 // 6
        )

        if not clickable_elements:
            logger.debug("未找到可点击的商品元素")
            return False

        # 随机选择一个元素点击
        element = random.choice(clickable_elements)
        center = element.get_center()
        if not center:
            return False

        x, y = center
        # 添加随机偏移
        x += random.randint(-self.click_offset_max_px, self.click_offset_max_px)
        y += random.randint(-self.click_offset_max_px, self.click_offset_max_px)

        logger.debug(f"点击随机商品: ({x}, {y})")
        return self.adb.tap(x, y)

    def _go_back_safely(self) -> bool:
        """
        安全返回（检查是否仍在淘宝内）

        Returns:
            是否仍在淘宝内
        """
        self.adb.press_back()
        self._random_sleep(1.0, 2.0)

        # 检查是否仍在淘宝
        if not self._is_in_taobao():
            logger.warning("返回操作导致离开淘宝，尝试重新打开")
            # 尝试重新打开淘宝
            self.adb.run_command(f"am start -n {self.TAOBAO_PACKAGE}/.MainTabActivity")
            self._random_sleep(2.0, 3.0)
            return self._is_in_taobao()

        return True

    def _go_to_home_tab(self) -> bool:
        """
        尝试回到淘宝首页标签

        Returns:
            是否成功
        """
        # 点击底部导航栏的"首页"按钮
        root = self.locator.dump_and_parse()
        if not root:
            return False

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            return False

        width, height = screen_size

        # 查找底部导航栏的首页按钮
        home_keywords = ['首页', '淘宝', 'Home']

        for node in root.iter():
            text = node.attrib.get('text', '')
            desc = node.attrib.get('content-desc', '')

            for keyword in home_keywords:
                if keyword in text or keyword in desc:
                    from .human_simulator import HumanSimulator
                    element = self.locator.find_element_by_text(root, keyword, exact=False)
                    if element:
                        center = element.get_center()
                        if center:
                            x, y = center
                            # 确保在底部区域
                            if y > height * 4 // 5:
                                logger.info("点击首页标签")
                                self.adb.tap(x, y)
                                self._random_sleep(1.5, 2.5)
                                return True

        return False

    def simulate_human_browse(self) -> bool:
        """
        模拟人类浏览商品行为

        整个过程持续 2-5 分钟，包括：
        - 随机上下滑动
        - 随机点击商品查看
        - 偶尔返回首页

        Returns:
            是否成功完成
        """
        if not self._is_in_taobao():
            logger.warning("当前不在淘宝 App 内，无法执行浏览模拟")
            return False

        # 随机决定浏览时长
        browse_duration = random.uniform(
            self.browse_duration_min * 60,  # 转换为秒
            self.browse_duration_max * 60
        )

        logger.info(f"开始模拟人类浏览行为，预计持续 {browse_duration / 60:.1f} 分钟")

        start_time = time.time()
        action_count = 0
        back_to_home_count = 0
        max_back_to_home = 2  # 最多回首页次数

        while time.time() - start_time < browse_duration:
            # 检查是否仍在淘宝
            if not self._is_in_taobao():
                logger.warning("离开淘宝，尝试返回")
                self.adb.run_command(f"am start -n {self.TAOBAO_PACKAGE}/.MainTabActivity")
                self._random_sleep(2.0, 3.0)
                if not self._is_in_taobao():
                    logger.error("无法返回淘宝，终止浏览模拟")
                    return False

            # 随机选择动作
            action = random.choices(
                ['scroll_up', 'scroll_down', 'click_product', 'wait', 'go_home'],
                weights=[30, 25, 25, 15, 5],  # 动作权重
                k=1
            )[0]

            action_count += 1
            logger.debug(f"执行动作 #{action_count}: {action}")

            if action == 'scroll_up':
                self._random_scroll('up')
                self._random_sleep(1.0, 2.5)

            elif action == 'scroll_down':
                self._random_scroll('down')
                self._random_sleep(1.0, 2.5)

            elif action == 'click_product':
                if self._find_and_click_random_product():
                    # 查看商品 2-5 秒
                    self._random_sleep(2.0, 5.0)
                    # 可能滚动查看详情
                    if random.random() < 0.5:
                        self._random_scroll('up')
                        self._random_sleep(1.0, 2.0)
                    # 返回
                    self._go_back_safely()
                else:
                    # 点击失败，滚动后重试
                    self._random_scroll('up')
                    self._random_sleep(1.0, 2.0)

            elif action == 'wait':
                self._random_sleep(2.0, 4.0)

            elif action == 'go_home':
                if back_to_home_count < max_back_to_home:
                    self._go_to_home_tab()
                    back_to_home_count += 1
                    self._random_sleep(1.5, 3.0)

        elapsed = time.time() - start_time
        logger.info(f"浏览模拟完成，持续 {elapsed / 60:.1f} 分钟，执行 {action_count} 个动作")

        return True

    def close_taobao(self) -> bool:
        """
        关闭淘宝进程

        Returns:
            是否成功
        """
        logger.info("关闭淘宝进程...")
        result = self.adb.force_stop_app(self.TAOBAO_PACKAGE)
        if result:
            logger.info("✓ 淘宝进程已关闭")
        else:
            logger.warning("⚠ 关闭淘宝进程可能失败")
        return result

    def execute_cycle_end_actions(self) -> bool:
        """
        执行周期结束后的动作

        包括：
        1. 模拟人类浏览
        2. 关闭淘宝进程

        Returns:
            是否成功
        """
        logger.info("=" * 60)
        logger.info("执行周期结束动作")
        logger.info("=" * 60)

        # 模拟人类浏览
        browse_success = self.simulate_human_browse()

        # 无论浏览是否成功，都关闭淘宝
        self.close_taobao()

        return browse_success

    # ==================== 点击偏移 ====================

    def apply_click_offset(self, x: int, y: int) -> Tuple[int, int]:
        """
        给点击坐标添加随机偏移

        Args:
            x: 原始 x 坐标
            y: 原始 y 坐标

        Returns:
            (new_x, new_y) 添加偏移后的坐标
        """
        offset_x = random.randint(-self.click_offset_max_px, self.click_offset_max_px)
        offset_y = random.randint(-self.click_offset_max_px, self.click_offset_max_px)
        return x + offset_x, y + offset_y
