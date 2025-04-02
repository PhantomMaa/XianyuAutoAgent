import requests
import json
import time
import os
import threading
from datetime import datetime    
from loguru import logger

# 存储 Cookie 的文件
COOKIE_FILE = "cookie.json"
# 刷新Cookie的URL
REFRESH_COOKIE_URL = "https://www.goofish.com/"
# Cookie检查间隔（秒）
CHECK_INTERVAL = 60 * 10  # 每10分钟检查一次
# Cookie有效期阈值（秒）
COOKIE_EXPIRY_THRESHOLD = 60 * 60 * 3  # 如果cookie已使用超过3小时，主动刷新

class CookieManager:
    """闲鱼Cookie管理器，负责检查和刷新Cookie"""
    
    def __init__(self, xianyu_api=None):
        """
        初始化Cookie管理器
        
        Args:
            xianyu_api: XianyuApis实例，用于检查token有效性
        """
        self.xianyu_api = xianyu_api
        self.cookies = None
        self.cookies_str = None
        self.device_id = None
        self.last_refresh_time = datetime.now().timestamp()
        self.refresh_lock = threading.Lock()
        self.refresh_thread = None
        self.stop_event = threading.Event()
        
        # 尝试从文件加载Cookie
        self._load_cookie_from_file()
        
        # 如果文件加载失败，尝试从环境变量加载
        if not self.cookies:
            self._load_cookie_from_env()
        
    def _load_cookie_from_file(self):
        """从文件加载Cookie"""
        try:
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE, "r") as f:
                    cookie_data = json.load(f)
                    if "cookies" in cookie_data and "cookies_str" in cookie_data:
                        self.cookies = cookie_data["cookies"]
                        self.cookies_str = cookie_data["cookies_str"]
                        self.device_id = cookie_data.get("device_id")
                        self.last_refresh_time = cookie_data.get("last_refresh_time", 
                                                               datetime.now().timestamp())
                        logger.info("成功从文件加载Cookie")
                        return True
        except Exception as e:
            logger.error(f"加载Cookie文件失败: {e}")
        
        return False
    
    def _load_cookie_from_env(self):
        """从环境变量加载Cookie"""
        try:
            cookies_str = os.getenv("COOKIES_STR")
            if cookies_str:
                # 导入这里避免循环导入
                from utils.xianyu_utils import trans_cookies
                
                self.cookies_str = cookies_str
                self.cookies = trans_cookies(cookies_str)
                
                # 获取用户ID并生成设备ID
                user_id = self.cookies.get('unb')
                if user_id:
                    from utils.xianyu_utils import generate_device_id
                    self.device_id = generate_device_id(user_id)
                
                logger.info("成功从环境变量加载Cookie")
                return True
        except Exception as e:
            logger.error(f"从环境变量加载Cookie失败: {e}")
        
        return False
    
    def _save_cookie_to_file(self):
        """将Cookie保存到文件"""
        try:
            cookie_data = {
                "cookies": self.cookies,
                "cookies_str": self.cookies_str,
                "device_id": self.device_id,
                "last_refresh_time": self.last_refresh_time
            }
            
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookie_data, f, indent=2)
            logger.info("成功保存Cookie到文件")
            return True
        except Exception as e:
            logger.error(f"保存Cookie文件失败: {e}")
            return False
    
    def set_cookies(self, cookies_dict, cookies_str, device_id=None):
        """
        设置Cookie
        
        Args:
            cookies_dict: Cookie字典
            cookies_str: Cookie字符串
            device_id: 设备ID
        """
        with self.refresh_lock:
            self.cookies = cookies_dict
            self.cookies_str = cookies_str
            if device_id:
                self.device_id = device_id
            self._save_cookie_to_file()
    
    def get_cookies(self):
        """获取当前Cookie"""
        return self.cookies, self.cookies_str, self.device_id
    
    def check_cookie_valid(self):
        """
        检查Cookie是否有效
        
        Returns:
            bool: Cookie是否有效
        """
        if not self.cookies or not self.xianyu_api:
            logger.warning("无法检查Cookie: Cookie或XianyuApi未设置")
            return False
            
        try:
            # 尝试获取token，如果失败则说明Cookie已过期
            token_response = self.xianyu_api.get_token(self.cookies, self.device_id)
            
            if token_response.get('ret') and token_response['ret'][0].startswith("SUCCESS"):
                # 检查Cookie使用时间是否接近过期
                current_time = datetime.now().timestamp()
                if current_time - self.last_refresh_time > COOKIE_EXPIRY_THRESHOLD:
                    logger.info(f"Cookie即将过期 (已使用{(current_time - self.last_refresh_time)/3600:.1f}小时)")
                    return False
                return True
            else:
                logger.error(f"Cookie已过期: {token_response}")
                return False
        except Exception as e:
            logger.error(f"检查Cookie时出错: {e}")
            return False
    
    def refresh_cookie_with_requests(self):
        """使用requests刷新Cookie"""
        with self.refresh_lock:
            logger.info("开始使用requests刷新Cookie...")
            
            try:
                # 加载现有可用的Cookie
                if not self.cookies:
                    if not self._load_cookie_from_file() and not self._load_cookie_from_env():
                        logger.error("无法加载Cookie: 当前没有可用的Cookie")
                        return False
                
                # 准备请求头
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Cookie": self.cookies_str
                }
                
                # 发送请求到闲鱼首页
                response = requests.get(REFRESH_COOKIE_URL, headers=headers, allow_redirects=True)
                
                # 获取响应中的所有Cookie
                cookies_dict = {}
                cookies_str_parts = []
                
                # 处理响应中的Set-Cookie头
                if 'Set-Cookie' in response.headers:
                    # 可能有多个Set-Cookie头
                    if isinstance(response.headers['Set-Cookie'], list):
                        for cookie_str in response.headers['Set-Cookie']:
                            cookie_name = cookie_str.split('=')[0].strip()
                            cookie_value = cookie_str.split('=')[1].split(';')[0].strip()
                            cookies_dict[cookie_name] = cookie_value
                            cookies_str_parts.append(f"{cookie_name}={cookie_value}")
                    else:
                        cookie_str = response.headers['Set-Cookie']
                        cookie_name = cookie_str.split('=')[0].strip()
                        cookie_value = cookie_str.split('=')[1].split(';')[0].strip()
                        cookies_dict[cookie_name] = cookie_value
                        cookies_str_parts.append(f"{cookie_name}={cookie_value}")
                else:
                    logger.error("无法获取到Set-Cookie头，刷新Cookie失败")
                    return False
                
                # 合并原有Cookie和新Cookie
                for name, value in self.cookies.items():
                    if name not in cookies_dict:
                        cookies_dict[name] = value
                        cookies_str_parts.append(f"{name}={value}")
                
                cookies_str = "; ".join(cookies_str_parts)
                
                # 更新Cookie
                self.cookies = cookies_dict
                self.cookies_str = cookies_str
                self.last_refresh_time = datetime.now().timestamp()
                
                # 保存Cookie
                self._save_cookie_to_file()
                
                logger.info("成功刷新Cookie")
                return True
                
            except Exception as e:
                logger.error(f"使用requests刷新Cookie失败: {e}")
                return False
    
    def refresh_cookie(self):
        """
        刷新Cookie，直接使用requests方法
        
        Returns:
            bool: 刷新是否成功
        """
        # 直接使用requests刷新
        return self.refresh_cookie_with_requests()
    
    def start_auto_refresh(self):
        """启动自动刷新线程"""
        if self.refresh_thread and self.refresh_thread.is_alive():
            logger.warning("自动刷新线程已在运行")
            return
        
        self.stop_event.clear()
        self.refresh_thread = threading.Thread(target=self._auto_refresh_loop)
        self.refresh_thread.daemon = True
        self.refresh_thread.start()
        logger.info("已启动自动刷新线程")
    
    def stop_auto_refresh(self):
        """停止自动刷新线程"""
        if self.refresh_thread and self.refresh_thread.is_alive():
            self.stop_event.set()
            self.refresh_thread.join(timeout=5)
            logger.info("已停止自动刷新线程")
    
    def _auto_refresh_loop(self):
        """自动刷新循环"""
        while not self.stop_event.is_set():
            try:
                # 检查Cookie是否有效
                if not self.check_cookie_valid():
                    logger.info("检测到Cookie无效，开始刷新...")
                    self.refresh_cookie()
                else:
                    logger.info("Cookie有效，无需刷新")
                
                # 等待下一次检查
                for _ in range(CHECK_INTERVAL):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"自动刷新过程中出错: {e}")
                # 出错后等待一段时间再重试
                time.sleep(60)


# 示例用法
if __name__ == "__main__":
    # 导入XianyuApis
    try:
        from XianyuApis import XianyuApis
        from utils.xianyu_utils import trans_cookies, generate_device_id
        
        # 初始化XianyuApis
        xianyu_api = XianyuApis()
        
        # 初始化CookieManager
        cookie_manager = CookieManager(xianyu_api)
        
        # 如果没有Cookie或Cookie无效，从环境变量获取
        
        if not cookie_manager.cookies or not cookie_manager.check_cookie_valid():
            cookies_str = os.getenv("COOKIES_STR")
            if cookies_str:
                cookies_dict = trans_cookies(cookies_str)
                user_id = cookies_dict.get('unb')
                device_id = generate_device_id(user_id) if user_id else None
                
                cookie_manager.set_cookies(cookies_dict, cookies_str, device_id)
                logger.info("已从环境变量加载Cookie")
            else:
                logger.error("环境变量中没有COOKIES_STR")
        
        # 启动自动刷新
        cookie_manager.start_auto_refresh()
        
        # 保持程序运行
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            cookie_manager.stop_auto_refresh()
            logger.info("程序已退出")
            
    except ImportError as e:
        logger.error(f"导入模块失败: {e}")
        logger.error("请确保已安装所有必要的依赖")
