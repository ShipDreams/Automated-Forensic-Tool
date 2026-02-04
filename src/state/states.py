#!/usr/bin/env python3
"""
页面状态定义
定义各平台的页面状态及其特征
"""

from enum import Enum, auto
from typing import List, Dict, Optional
from dataclasses import dataclass, field


class PageState(Enum):
    """通用页面状态"""
    UNKNOWN = auto()           # 未知状态
    LOADING = auto()           # 加载中
    ERROR = auto()             # 错误页面

    # 系统页面
    HOME_SCREEN = auto()       # 手机桌面
    APP_STORE = auto()         # 应用商店
    APP_STORE_SEARCH = auto()  # 应用商店搜索结果
    BROWSER = auto()           # 浏览器

    # 通用 App 页面
    APP_HOME = auto()          # App 首页
    APP_SEARCH = auto()        # App 搜索页
    APP_SEARCH_INPUT = auto()  # 搜索输入框激活

    # 商品相关
    PRODUCT_PAGE = auto()      # 商品详情页
    PRODUCT_VIDEO = auto()     # 商品视频播放
    PRODUCT_IMAGES = auto()    # 商品图片浏览

    # 店铺相关
    SHOP_PAGE = auto()         # 店铺首页
    SHOP_INFO = auto()         # 店铺信息
    SHOP_QUALIFICATION = auto()  # 店铺资质页

    # 风控相关
    CAPTCHA = auto()           # 验证码页
    LOGIN_REQUIRED = auto()    # 需要登录
    BLOCKED = auto()           # 被封禁
    RATE_LIMITED = auto()      # 频率限制

    # 弹窗
    POPUP_AD = auto()          # 广告弹窗
    POPUP_PERMISSION = auto()  # 权限请求弹窗
    POPUP_UPDATE = auto()      # 更新提示弹窗
    POPUP_OTHER = auto()       # 其他弹窗


@dataclass
class StateFeature:
    """
    状态特征

    用于描述某个页面状态的识别特征。
    """
    # 文本特征
    required_texts: List[str] = field(default_factory=list)  # 必须包含的文本
    optional_texts: List[str] = field(default_factory=list)  # 可选文本（有助于判断）
    excluded_texts: List[str] = field(default_factory=list)  # 不能包含的文本

    # UI 元素特征
    required_elements: List[Dict] = field(default_factory=list)  # 必须存在的元素
    optional_elements: List[Dict] = field(default_factory=list)  # 可选元素

    # 包名特征
    package_patterns: List[str] = field(default_factory=list)  # 包名匹配模式

    # Activity 特征
    activity_patterns: List[str] = field(default_factory=list)  # Activity 匹配模式

    # 置信度阈值
    confidence_threshold: float = 0.6


@dataclass
class StateDefinition:
    """
    状态定义

    将 PageState 枚举与其特征关联。
    """
    state: PageState
    features: StateFeature
    description: str = ""
    platform: str = "common"  # common 表示通用，或具体平台名


# ==================== 通用状态特征 ====================

COMMON_STATES: Dict[PageState, StateDefinition] = {
    PageState.CAPTCHA: StateDefinition(
        state=PageState.CAPTCHA,
        features=StateFeature(
            required_texts=['验证码', '滑动验证', '安全验证', 'captcha', '拼图'],
            optional_texts=['向右滑动', '请完成验证', '点击验证'],
        ),
        description="验证码页面"
    ),

    PageState.LOGIN_REQUIRED: StateDefinition(
        state=PageState.LOGIN_REQUIRED,
        features=StateFeature(
            required_texts=['登录', '请登录', '登录后查看'],
            optional_texts=['注册', '密码', '手机号', '验证码登录'],
            required_elements=[
                {'clickable': 'true', 'text_pattern': '登录|login'}
            ]
        ),
        description="需要登录"
    ),

    PageState.BLOCKED: StateDefinition(
        state=PageState.BLOCKED,
        features=StateFeature(
            required_texts=['账号异常', '暂时无法访问', '违规', '封禁'],
        ),
        description="账号被封禁"
    ),

    PageState.RATE_LIMITED: StateDefinition(
        state=PageState.RATE_LIMITED,
        features=StateFeature(
            required_texts=['操作频繁', '请稍后再试', '访问过于频繁'],
        ),
        description="频率限制"
    ),

    PageState.LOADING: StateDefinition(
        state=PageState.LOADING,
        features=StateFeature(
            optional_texts=['加载中', '正在加载', 'loading'],
            optional_elements=[
                {'class': 'ProgressBar'}
            ]
        ),
        description="页面加载中"
    ),

    PageState.POPUP_AD: StateDefinition(
        state=PageState.POPUP_AD,
        features=StateFeature(
            optional_texts=['广告', '跳过', '关闭', '×', 'X'],
            optional_elements=[
                {'resource-id_pattern': 'close|skip|dismiss'}
            ]
        ),
        description="广告弹窗"
    ),

    PageState.POPUP_PERMISSION: StateDefinition(
        state=PageState.POPUP_PERMISSION,
        features=StateFeature(
            required_texts=['允许', '拒绝', '权限'],
            optional_texts=['通知', '位置', '相机', '存储'],
        ),
        description="权限请求弹窗"
    ),
}


# ==================== 淘宝状态特征 ====================

TAOBAO_STATES: Dict[PageState, StateDefinition] = {
    PageState.APP_HOME: StateDefinition(
        state=PageState.APP_HOME,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            optional_texts=['淘宝', '首页', '推荐', '关注'],
            optional_elements=[
                {'resource-id': 'com.taobao.taobao:id/home_searchedit'}
            ]
        ),
        description="淘宝首页",
        platform="taobao"
    ),

    PageState.APP_SEARCH: StateDefinition(
        state=PageState.APP_SEARCH,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            optional_texts=['搜索', '取消'],
            optional_elements=[
                {'resource-id_pattern': 'search.*input|searchedit'}
            ]
        ),
        description="淘宝搜索页",
        platform="taobao"
    ),

    PageState.PRODUCT_PAGE: StateDefinition(
        state=PageState.PRODUCT_PAGE,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            optional_texts=['加入购物车', '立即购买', '店铺', '客服', '收藏'],
            optional_elements=[
                {'resource-id_pattern': 'detail|product'}
            ]
        ),
        description="淘宝商品详情页",
        platform="taobao"
    ),

    PageState.SHOP_PAGE: StateDefinition(
        state=PageState.SHOP_PAGE,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            optional_texts=['关注店铺', '全部宝贝', '店铺动态', '资质证照'],
        ),
        description="淘宝店铺页",
        platform="taobao"
    ),

    PageState.SHOP_QUALIFICATION: StateDefinition(
        state=PageState.SHOP_QUALIFICATION,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            required_texts=['资质证照', '营业执照', '经营许可'],
            optional_texts=['食品经营', '工商注册'],
        ),
        description="淘宝店铺资质页",
        platform="taobao"
    ),
}


# ==================== 京东状态特征 ====================

JD_STATES: Dict[PageState, StateDefinition] = {
    PageState.APP_HOME: StateDefinition(
        state=PageState.APP_HOME,
        features=StateFeature(
            package_patterns=['com.jingdong.app.mall'],
            optional_texts=['京东', '首页', '发现', '购物车'],
        ),
        description="京东首页",
        platform="jd"
    ),

    PageState.PRODUCT_PAGE: StateDefinition(
        state=PageState.PRODUCT_PAGE,
        features=StateFeature(
            package_patterns=['com.jingdong.app.mall'],
            optional_texts=['加入购物车', '立即购买', '店铺', '客服'],
        ),
        description="京东商品详情页",
        platform="jd"
    ),
}


# ==================== 抖音状态特征 ====================

DOUYIN_STATES: Dict[PageState, StateDefinition] = {
    PageState.APP_HOME: StateDefinition(
        state=PageState.APP_HOME,
        features=StateFeature(
            package_patterns=['com.ss.android.ugc.aweme'],
            optional_texts=['首页', '朋友', '消息', '我'],
        ),
        description="抖音首页",
        platform="douyin"
    ),

    PageState.PRODUCT_PAGE: StateDefinition(
        state=PageState.PRODUCT_PAGE,
        features=StateFeature(
            package_patterns=['com.ss.android.ugc.aweme'],
            optional_texts=['立即购买', '加入购物车', '商品详情'],
        ),
        description="抖音商品详情页",
        platform="douyin"
    ),
}


def get_all_states_for_platform(platform: str = None) -> Dict[PageState, StateDefinition]:
    """
    获取指定平台的所有状态定义

    Args:
        platform: 平台名称，None 表示所有

    Returns:
        状态定义字典
    """
    result = dict(COMMON_STATES)

    if platform is None or platform == 'taobao':
        result.update(TAOBAO_STATES)

    if platform is None or platform == 'jd':
        result.update(JD_STATES)

    if platform is None or platform == 'douyin':
        result.update(DOUYIN_STATES)

    return result
