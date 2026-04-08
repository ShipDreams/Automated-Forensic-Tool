#!/usr/bin/env python3
"""
基础单元测试
测试不需要设备连接的模块
"""

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class TestPlatformRouter(unittest.TestCase):
    """测试平台路由器"""

    def setUp(self):
        from platforms.router import PlatformRouter
        self.router = PlatformRouter(None, None, None)

    def test_detect_taobao(self):
        """测试淘宝链接识别"""
        urls = [
            'https://item.taobao.com/item.htm?id=123',
            'https://detail.tmall.com/item.htm?id=456',
            'https://m.taobao.com/xxx',
            'https://a.m.taobao.com/xxx',
        ]
        for url in urls:
            result = self.router.detect_platform(url)
            self.assertEqual(result, 'taobao', f"URL {url} 应识别为 taobao")

    def test_detect_jd(self):
        """测试京东链接识别"""
        urls = [
            'https://item.jd.com/123.html',
            'https://m.jd.com/product/xxx',
            'https://3.cn/xxx',
        ]
        for url in urls:
            result = self.router.detect_platform(url)
            self.assertEqual(result, 'jd', f"URL {url} 应识别为 jd")

    def test_detect_douyin(self):
        """测试抖音链接识别"""
        urls = [
            'https://v.douyin.com/xxx',
            'https://www.douyin.com/xxx',
            'https://m.douyin.com/xxx',
        ]
        for url in urls:
            result = self.router.detect_platform(url)
            self.assertEqual(result, 'douyin', f"URL {url} 应识别为 douyin")

    def test_detect_alibaba(self):
        """测试 1688 链接识别"""
        urls = [
            'https://detail.1688.com/offer/xxx',
            'https://m.1688.com/xxx',
        ]
        for url in urls:
            result = self.router.detect_platform(url)
            self.assertEqual(result, 'alibaba', f"URL {url} 应识别为 alibaba")

    def test_detect_unknown(self):
        """测试未知链接"""
        urls = [
            'https://www.google.com',
            'https://www.baidu.com',
            'https://unknown.site.com/product/123',
        ]
        for url in urls:
            result = self.router.detect_platform(url)
            self.assertIsNone(result, f"URL {url} 应返回 None")

    def test_supported_platforms(self):
        """测试支持的平台列表"""
        supported = self.router.get_supported_platforms()
        self.assertIn('taobao', supported)

    def test_all_platforms(self):
        """测试所有平台列表"""
        all_platforms = self.router.get_all_platforms()
        self.assertIn('taobao', all_platforms)
        self.assertIn('jd', all_platforms)
        self.assertIn('douyin', all_platforms)
        self.assertIn('alibaba', all_platforms)


class TestTaskModel(unittest.TestCase):
    """测试任务模型"""

    def test_create_task(self):
        """测试创建任务"""
        from task import Task, TaskStatus
        task = Task.from_url('https://item.taobao.com/item.htm?id=123')

        self.assertIsNotNone(task.id)
        self.assertEqual(task.product_url, 'https://item.taobao.com/item.htm?id=123')
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.retry_count, 0)

    def test_task_lifecycle(self):
        """测试任务生命周期"""
        from task import Task, TaskStatus, TaskResult

        task = Task.from_url('https://item.taobao.com/item.htm?id=123')

        # 开始执行
        task.mark_running()
        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertIsNotNone(task.started_at)

        # 完成
        task.mark_completed(TaskResult(success=True, message="OK"))
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(task.completed_at)
        self.assertTrue(task.result.success)

    def test_task_retry(self):
        """测试任务重试"""
        from task import Task, TaskStatus

        task = Task.from_url('https://item.taobao.com/item.htm?id=123', max_retries=3)

        # 第一次失败
        task.mark_failed("Error 1", can_retry=True)
        self.assertEqual(task.status, TaskStatus.RETRY)
        self.assertEqual(task.retry_count, 1)

        # 第二次失败
        task.mark_failed("Error 2", can_retry=True)
        self.assertEqual(task.status, TaskStatus.RETRY)
        self.assertEqual(task.retry_count, 2)

        # 第三次失败
        task.mark_failed("Error 3", can_retry=True)
        self.assertEqual(task.status, TaskStatus.RETRY)
        self.assertEqual(task.retry_count, 3)

        # 第四次失败 - 超过重试次数
        task.mark_failed("Error 4", can_retry=True)
        self.assertEqual(task.status, TaskStatus.FAILED)

    def test_task_serialization(self):
        """测试任务序列化"""
        from task import Task

        task = Task.from_url('https://item.taobao.com/item.htm?id=123')
        task_dict = task.to_dict()

        self.assertEqual(task_dict['product_url'], 'https://item.taobao.com/item.htm?id=123')
        self.assertEqual(task_dict['status'], 'pending')

        # 反序列化
        task2 = Task.from_dict(task_dict)
        self.assertEqual(task2.product_url, task.product_url)
        self.assertEqual(task2.id, task.id)


class TestRiskDetector(unittest.TestCase):
    """测试风险检测器"""

    def setUp(self):
        from antibot.risk_detector import RiskDetector
        self.detector = RiskDetector()

    def test_keywords_loaded(self):
        """测试关键词加载"""
        self.assertIn('验证码', self.detector.captcha_keywords)
        self.assertIn('登录', self.detector.login_keywords)
        self.assertIn('操作频繁', self.detector.rate_limit_keywords)

    def test_risk_type_enum(self):
        """测试风险类型枚举"""
        from antibot.risk_detector import RiskType

        self.assertEqual(RiskType.CAPTCHA.value, 'captcha')
        self.assertEqual(RiskType.LOGIN_REQUIRED.value, 'login_required')
        self.assertEqual(RiskType.RATE_LIMIT.value, 'rate_limit')


class TestHumanSimulator(unittest.TestCase):
    """测试人类行为模拟器"""

    def setUp(self):
        from antibot.human_simulator import HumanSimulator
        self.simulator = HumanSimulator()

    def test_random_sleep(self):
        """测试随机延迟"""
        import time
        start = time.time()
        delay = self.simulator.random_sleep(100, 200)
        elapsed = time.time() - start

        self.assertGreaterEqual(delay, 0.1)
        self.assertLessEqual(delay, 0.2)
        self.assertGreaterEqual(elapsed, 0.1)

    def test_random_offset(self):
        """测试随机偏移"""
        x, y = 500, 800
        new_x, new_y = self.simulator.apply_offset_to_point(x, y, max_offset=10)

        self.assertGreaterEqual(new_x, x - 10)
        self.assertLessEqual(new_x, x + 10)
        self.assertGreaterEqual(new_y, y - 10)
        self.assertLessEqual(new_y, y + 10)

    def test_scroll_params(self):
        """测试滚动参数"""
        params = self.simulator.get_random_scroll_params(1080, 1920, 'up')

        start_x, start_y, end_x, end_y, duration = params

        self.assertGreater(start_x, 0)
        self.assertLess(start_x, 1080)
        self.assertGreater(start_y, 0)
        self.assertLess(start_y, 1920)
        self.assertGreater(duration, 0)


class TestStateDetector(unittest.TestCase):
    """测试状态检测器"""

    def setUp(self):
        from state import StateDetector, PageState
        self.detector = StateDetector('taobao')
        self.PageState = PageState

    def test_state_definitions_loaded(self):
        """测试状态定义加载"""
        self.assertGreater(len(self.detector.state_definitions), 0)

    def test_is_risk_state(self):
        """测试风险状态判断"""
        self.assertTrue(self.detector.is_risk_state(self.PageState.CAPTCHA))
        self.assertTrue(self.detector.is_risk_state(self.PageState.LOGIN_REQUIRED))
        self.assertTrue(self.detector.is_risk_state(self.PageState.BLOCKED))
        self.assertFalse(self.detector.is_risk_state(self.PageState.APP_HOME))

    def test_is_popup_state(self):
        """测试弹窗状态判断"""
        self.assertTrue(self.detector.is_popup_state(self.PageState.POPUP_AD))
        self.assertTrue(self.detector.is_popup_state(self.PageState.POPUP_PERMISSION))
        self.assertFalse(self.detector.is_popup_state(self.PageState.PRODUCT_PAGE))


class TestCooldownManager(unittest.TestCase):
    """测试冷却管理器"""

    def test_initial_state(self):
        """测试初始状态"""
        from antibot.cooldown import CooldownManager
        import tempfile
        import os

        # 使用临时文件
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            state_file = f.name

        try:
            manager = CooldownManager(state_file=state_file)

            self.assertFalse(manager.is_cooling_down())
            self.assertTrue(manager.can_execute_task())
            self.assertEqual(manager.continuous_tasks, 0)
        finally:
            if os.path.exists(state_file):
                os.remove(state_file)

    def test_trigger_cooldown(self):
        """测试触发冷却"""
        from antibot.cooldown import CooldownManager
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            state_file = f.name

        try:
            manager = CooldownManager(
                config={'enabled': True, 'duration_minutes': 1},
                state_file=state_file
            )

            manager.trigger_cooldown("test", duration_minutes=1)

            self.assertTrue(manager.is_cooling_down())
            self.assertFalse(manager.can_execute_task())

            remaining = manager.get_remaining_cooldown()
            self.assertIsNotNone(remaining)
            self.assertGreater(remaining.total_seconds(), 0)

            # 重置
            manager.reset()
            self.assertFalse(manager.is_cooling_down())
        finally:
            if os.path.exists(state_file):
                os.remove(state_file)


class TestGroupedExecutor(unittest.TestCase):
    """测试分组执行器的动态补位逻辑"""

    def test_invalid_link_does_not_break_shop_group_fill(self):
        from task import Task
        from task.grouped_executor import GroupResult, GroupedExecutor
        from task.shop_grouper import EvidenceGroup

        tasks = [
            Task.from_url('https://example.com/24138', shop_name='测试3店'),
            Task.from_url('https://example.com/24139', shop_name='测试3店', metadata={'invalid': True}),
            Task.from_url('https://example.com/24141', shop_name='测试3店'),
            Task.from_url('https://example.com/24142', shop_name='测试3店'),
        ]

        groups = [
            EvidenceGroup(shop_name='测试3店', group_index=1, tasks=tasks[:3]),
            EvidenceGroup(shop_name='测试3店', group_index=2, tasks=tasks[3:]),
        ]

        class StubExecutor(GroupedExecutor):
            def _phase1_collect_favorites(self, group, task_source=None):
                source = task_source if task_source is not None else group.tasks
                processed = []
                valid = []
                for task in source:
                    processed.append(task)
                    task.group_id = f"{group.shop_name}_{group.group_index}"
                    if task.metadata.get('invalid'):
                        task.is_valid = False
                        group.invalid_tasks.append(task)
                    else:
                        task.is_valid = True
                        valid.append(task)
                    if len(valid) >= self.group_size:
                        break
                group.tasks = processed
                return valid

            def _phase2_record_evidence(self, group, video_duration=30):
                return GroupResult(
                    success=True,
                    evidence_name=group.evidence_name,
                    valid_count=len(group.valid_tasks),
                    invalid_count=len(group.invalid_tasks),
                )

            def _cleanup_between_groups(self):
                return None

        executor = StubExecutor(None, None, None, group_size=3)
        results = executor.execute_all_groups(groups=groups, video_duration=30)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].valid_count, 3)
        self.assertEqual(results[0].invalid_count, 1)
        self.assertEqual(tasks[3].group_id, '测试3店_1')


class TestTaobaoFavorites(unittest.TestCase):
    """测试淘宝收藏夹点击策略"""

    def test_click_favorite_item_uses_scroll_then_fixed_slot(self):
        from platforms.taobao_favorites import TaobaoFavorites

        class FakeADB:
            def __init__(self):
                self.taps = []
                self.swipes = []

            def get_screen_size(self):
                return (1080, 2400)

            def tap(self, x, y):
                self.taps.append((x, y))
                return True

            def swipe(self, x1, y1, x2, y2, duration_ms=300):
                self.swipes.append((x1, y1, x2, y2, duration_ms))
                return True

        adb = FakeADB()
        favorites = TaobaoFavorites(adb, ui_locator=object())

        with patch.object(favorites, '_sleep', return_value=None), \
             patch.object(favorites, '_is_on_favorites_page', return_value=False):
            success = favorites.click_favorite_item(2)

        self.assertTrue(success)
        self.assertEqual(len(adb.swipes), 2)
        self.assertEqual(adb.swipes[0], (324, 1008, 324, 480, 340))
        self.assertEqual(adb.swipes[1], (324, 1008, 324, 480, 340))
        self.assertEqual(adb.taps, [(302, 576)])

    def test_add_to_favorites_prefers_template_without_dump(self):
        from platforms.taobao_favorites import TaobaoFavorites

        class FakeImageLocator:
            def __init__(self):
                self.calls = []

            def template_exists(self, name):
                self.calls.append(('template_exists', name))
                return name == 'favorite_btn'

            def find_and_click(self, name, threshold=0.7, max_attempts=3):
                self.calls.append(('find_and_click', name, threshold, max_attempts))
                return True

        class FakeLocator:
            def __init__(self, img):
                self.img = img

            def _get_image_locator(self):
                return self.img

            def dump_and_parse(self):
                raise AssertionError("dump_and_parse should not be called when template exists")

        img = FakeImageLocator()
        favorites = TaobaoFavorites(adb_controller=object(), ui_locator=FakeLocator(img))

        with patch.object(favorites, '_sleep', return_value=None):
            success = favorites.add_to_favorites()

        self.assertTrue(success)
        self.assertEqual(
            img.calls,
            [
                ('template_exists', 'favorite_btn'),
                ('find_and_click', 'favorite_btn', 0.7, 3),
            ]
        )

    def test_add_to_favorites_retries_once_after_ad_popup_close(self):
        from platforms.taobao_favorites import TaobaoFavorites

        class FakeImageLocator:
            def __init__(self):
                self.calls = []
                self.favorite_clicks = 0

            def template_exists(self, name):
                self.calls.append(('template_exists', name))
                return name in {'favorite_btn', 'del_ads'}

            def find_and_click(self, name, threshold=0.7, max_attempts=3):
                self.calls.append(('find_and_click', name, threshold, max_attempts))
                if name == 'favorite_btn':
                    self.favorite_clicks += 1
                    return self.favorite_clicks == 2
                return True

        class FakeLocator:
            def __init__(self, img):
                self.img = img

            def _get_image_locator(self):
                return self.img

            def dump_and_parse(self):
                raise AssertionError("dump_and_parse should not be called in template retry path")

        img = FakeImageLocator()
        favorites = TaobaoFavorites(adb_controller=object(), ui_locator=FakeLocator(img))

        with patch.object(favorites, '_sleep', return_value=None):
            success = favorites.add_to_favorites()

        self.assertTrue(success)
        self.assertIn(('find_and_click', 'del_ads', 0.85, 1), img.calls)
        self.assertEqual(img.favorite_clicks, 2)


class TestTaobaoHandler(unittest.TestCase):
    """测试淘宝详情页视频处理策略"""

    def test_replay_video_from_start_only_uses_image_unmute(self):
        from platforms.taobao_handler import TaobaoHandler

        class FakeImageLocator:
            def __init__(self):
                self.calls = []

            def template_exists(self, name):
                self.calls.append(('template_exists', name))
                return True

            def find_and_click(self, name, threshold=0.75, max_attempts=2):
                self.calls.append(('find_and_click', name, threshold, max_attempts))
                return True

        class FakeLocator:
            def __init__(self, img):
                self.img = img

            def _get_image_locator(self):
                return self.img

        img = FakeImageLocator()
        handler = TaobaoHandler(adb_controller=object(), ui_locator=FakeLocator(img))

        with patch.object(handler, '_sleep', return_value=None):
            success = handler.replay_video_from_start()

        self.assertTrue(success)
        self.assertEqual(
            img.calls,
            [
                ('template_exists', 'mute_btn'),
                ('find_and_click', 'mute_btn', 0.7, 3),
            ]
        )

    def test_view_shop_info_retries_once_after_ad_popup_close(self):
        from platforms.taobao_handler import TaobaoHandler

        class FakeImageLocator:
            def __init__(self):
                self.calls = []
                self.shop_clicks = 0

            def template_exists(self, name):
                self.calls.append(('template_exists', name))
                return name in {'shop_btn', 'del_ads'}

            def find_and_click(self, name, threshold=0.75, max_attempts=3):
                self.calls.append(('find_and_click', name, threshold, max_attempts))
                if name == 'shop_btn':
                    self.shop_clicks += 1
                    return self.shop_clicks == 2
                return True

        class FakeLocator:
            def __init__(self, img):
                self.img = img

            def _get_image_locator(self):
                return self.img

        handler = TaobaoHandler(adb_controller=object(), ui_locator=FakeLocator(FakeImageLocator()))

        with patch.object(handler, '_sleep_after_click', return_value=None), \
             patch.object(handler, '_sleep', return_value=None), \
             patch.object(handler, '_navigate_to_shop_home', return_value=True):
            success = handler.view_shop_info()

        self.assertTrue(success)


if __name__ == '__main__':
    unittest.main(verbosity=2)
