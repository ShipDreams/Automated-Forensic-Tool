#!/usr/bin/env python3
"""
Page State Definitions
Defines page states and their features for various platforms.
"""

from enum import Enum, auto
from typing import List, Dict, Optional
from dataclasses import dataclass, field


class PageState(Enum):
    """Common page states."""
    UNKNOWN = auto()           # Unknown state
    LOADING = auto()           # Loading
    ERROR = auto()             # Error page

    # System pages
    HOME_SCREEN = auto()       # Phone home screen
    APP_STORE = auto()         # App store
    APP_STORE_SEARCH = auto()  # App store search results
    BROWSER = auto()           # Browser

    # Common App pages
    APP_HOME = auto()          # App home page
    APP_SEARCH = auto()        # App search page
    APP_SEARCH_INPUT = auto()  # Search input activated

    # Product related
    PRODUCT_PAGE = auto()      # Product detail page
    PRODUCT_VIDEO = auto()     # Product video playback
    PRODUCT_IMAGES = auto()    # Product image browsing

    # Shop related
    SHOP_PAGE = auto()         # Shop home page
    SHOP_INFO = auto()         # Shop info
    SHOP_QUALIFICATION = auto()  # Shop qualification page

    # Risk control related
    CAPTCHA = auto()           # Captcha page
    LOGIN_REQUIRED = auto()    # Login required
    BLOCKED = auto()           # Blocked
    RATE_LIMITED = auto()      # Rate limited

    # Popups
    POPUP_AD = auto()          # Ad popup
    POPUP_PERMISSION = auto()  # Permission request popup
    POPUP_UPDATE = auto()      # Update prompt popup
    POPUP_OTHER = auto()       # Other popup


@dataclass
class StateFeature:
    """
    State Feature

    Used to describe identifying features of a page state.
    """
    # Text features
    required_texts: List[str] = field(default_factory=list)  # Must contain these texts
    optional_texts: List[str] = field(default_factory=list)  # Optional texts (helps identification)
    excluded_texts: List[str] = field(default_factory=list)  # Must not contain these texts

    # UI element features
    required_elements: List[Dict] = field(default_factory=list)  # Must exist elements
    optional_elements: List[Dict] = field(default_factory=list)  # Optional elements

    # Package name features
    package_patterns: List[str] = field(default_factory=list)  # Package name patterns

    # Activity features
    activity_patterns: List[str] = field(default_factory=list)  # Activity patterns

    # Confidence threshold
    confidence_threshold: float = 0.6


@dataclass
class StateDefinition:
    """
    State Definition

    Associates PageState enum with its features.
    """
    state: PageState
    features: StateFeature
    description: str = ""
    platform: str = "common"  # common for generic, or specific platform name


# ==================== Common State Features ====================

COMMON_STATES: Dict[PageState, StateDefinition] = {
    PageState.CAPTCHA: StateDefinition(
        state=PageState.CAPTCHA,
        features=StateFeature(
            required_texts=['验证码', '滑动验证', '安全验证', 'captcha', '拼图'],
            optional_texts=['向右滑动', '请完成验证', '点击验证'],
        ),
        description="Captcha page"
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
        description="Login required"
    ),

    PageState.BLOCKED: StateDefinition(
        state=PageState.BLOCKED,
        features=StateFeature(
            required_texts=['账号异常', '暂时无法访问', '违规', '封禁'],
        ),
        description="Account blocked"
    ),

    PageState.RATE_LIMITED: StateDefinition(
        state=PageState.RATE_LIMITED,
        features=StateFeature(
            required_texts=['操作频繁', '请稍后再试', '访问过于频繁'],
        ),
        description="Rate limited"
    ),

    PageState.LOADING: StateDefinition(
        state=PageState.LOADING,
        features=StateFeature(
            optional_texts=['加载中', '正在加载', 'loading'],
            optional_elements=[
                {'class': 'ProgressBar'}
            ]
        ),
        description="Page loading"
    ),

    PageState.POPUP_AD: StateDefinition(
        state=PageState.POPUP_AD,
        features=StateFeature(
            optional_texts=['广告', '跳过', '关闭', '×', 'X'],
            optional_elements=[
                {'resource-id_pattern': 'close|skip|dismiss'}
            ]
        ),
        description="Ad popup"
    ),

    PageState.POPUP_PERMISSION: StateDefinition(
        state=PageState.POPUP_PERMISSION,
        features=StateFeature(
            required_texts=['允许', '拒绝', '权限'],
            optional_texts=['通知', '位置', '相机', '存储'],
        ),
        description="Permission request popup"
    ),
}


# ==================== Taobao State Features ====================

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
        description="Taobao home page",
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
        description="Taobao search page",
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
        description="Taobao product detail page",
        platform="taobao"
    ),

    PageState.SHOP_PAGE: StateDefinition(
        state=PageState.SHOP_PAGE,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            optional_texts=['关注店铺', '全部宝贝', '店铺动态', '资质证照'],
        ),
        description="Taobao shop page",
        platform="taobao"
    ),

    PageState.SHOP_QUALIFICATION: StateDefinition(
        state=PageState.SHOP_QUALIFICATION,
        features=StateFeature(
            package_patterns=['com.taobao.taobao'],
            required_texts=['资质证照', '营业执照', '经营许可'],
            optional_texts=['食品经营', '工商注册'],
        ),
        description="Taobao shop qualification page",
        platform="taobao"
    ),
}


# ==================== JD State Features ====================

JD_STATES: Dict[PageState, StateDefinition] = {
    PageState.APP_HOME: StateDefinition(
        state=PageState.APP_HOME,
        features=StateFeature(
            package_patterns=['com.jingdong.app.mall'],
            optional_texts=['京东', '首页', '发现', '购物车'],
        ),
        description="JD home page",
        platform="jd"
    ),

    PageState.PRODUCT_PAGE: StateDefinition(
        state=PageState.PRODUCT_PAGE,
        features=StateFeature(
            package_patterns=['com.jingdong.app.mall'],
            optional_texts=['加入购物车', '立即购买', '店铺', '客服'],
        ),
        description="JD product detail page",
        platform="jd"
    ),
}


# ==================== Douyin State Features ====================

DOUYIN_STATES: Dict[PageState, StateDefinition] = {
    PageState.APP_HOME: StateDefinition(
        state=PageState.APP_HOME,
        features=StateFeature(
            package_patterns=['com.ss.android.ugc.aweme'],
            optional_texts=['首页', '朋友', '消息', '我'],
        ),
        description="Douyin home page",
        platform="douyin"
    ),

    PageState.PRODUCT_PAGE: StateDefinition(
        state=PageState.PRODUCT_PAGE,
        features=StateFeature(
            package_patterns=['com.ss.android.ugc.aweme'],
            optional_texts=['立即购买', '加入购物车', '商品详情'],
        ),
        description="Douyin product detail page",
        platform="douyin"
    ),
}


def get_all_states_for_platform(platform: str = None) -> Dict[PageState, StateDefinition]:
    """
    Get all state definitions for specified platform.

    Args:
        platform: Platform name, None for all

    Returns:
        State definition dictionary
    """
    result = dict(COMMON_STATES)

    if platform is None or platform == 'taobao':
        result.update(TAOBAO_STATES)

    if platform is None or platform == 'jd':
        result.update(JD_STATES)

    if platform is None or platform == 'douyin':
        result.update(DOUYIN_STATES)

    return result
