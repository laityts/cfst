"""
Cloudflare Speed Test 自动化测试脚本

功能：
1. 节点测速与结果处理（分协议类型执行）
2. 自动更新Cloudflare DNS记录（动态域名生成）
3. 多协议支持（IPv4/IPv6/Proxy）
4. 多地区码/多端口支持
5. 日志管理与结果同步
"""

# 初始化颜色输出库
from colorama import init, Fore, Style
init(autoreset=True)

# 标准库导入
import os
import sys
import platform  # 用于获取系统架构信息
import logging   # 日志记录
import random    # 随机选择端口
import csv       # CSV文件处理
import re        # 正则表达式
import json      # JSON处理
import argparse  # 命令行参数解析
import requests  # HTTP请求
import subprocess  # 执行外部命令
import unittest  # 单元测试
from pathlib import Path  # 路径操作
from datetime import datetime  # 时间处理
from dotenv import load_dotenv  # 环境变量加载
from urllib.parse import urlparse  # URL解析
from unittest.mock import patch, Mock  # 单元测试模拟
from subprocess import CompletedProcess  # 进程结果处理

# 从本地模块导入
from py.colo_emojis import colo_emojis  # 地区码对应的表情符号
from py.tg import send_message_with_fallback  # Telegram通知功能

# ---------------------------- 配置参数 ----------------------------
# 系统架构映射表（用于选择正确的二进制文件）
ARCH_MAP = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "armv7l": "armv7"
}

# 支持的Cloudflare地区码列表
CFCOLO_LIST = ["HKG", "LAX", "FRA"]  
# Cloudflare端口列表（支持多个端口）
CLOUDFLARE_PORTS = [443]  
# 默认测速参数：延迟阈值、丢包率等
DEFAULT_PARAMS = {
    "tl": 500,   # 延迟阈值（ms）
    "tll": 30,   # 最低延迟要求
    "tlr": 0.2,  # 最大丢包率
    "n": 500,    # 测试节点数
    "dn": 3,     # 下载测试次数
    "p": 3       # 并发数
}

# ---------------------------- 路径配置 ----------------------------
BASE_DIR = Path(__file__).parent.resolve()  # 项目根目录
LOGS_DIR = BASE_DIR / "logs"                # 日志目录
RESULTS_DIR = BASE_DIR / "results"          # 原始结果目录
SPEED_DIR = BASE_DIR / "speed"              # 处理后的结果目录

# ---------------------------- 初始化环境 ----------------------------
load_dotenv()  # 从.env文件加载环境变量

# ---------------------------- 工具函数 ----------------------------
class Color:
    """ANSI 颜色代码控制类"""
    RED = '\033[91m'     # 红色
    GREEN = '\033[92m'   # 绿色
    YELLOW = '\033[93m'  # 黄色
    CYAN = '\033[96m'    # 青色
    RESET = '\033[0m'    # 重置样式
    BOLD = '\033[1m'     # 粗体

def setup_logging(ip_type: str):
    """初始化日志系统（按协议类型分目录存储）
    
    参数:
        ip_type: 协议类型 (ipv4/ipv6/proxy)
    """
    # 创建日志目录
    log_dir = LOGS_DIR / ip_type
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 清理历史日志文件
    for old_log in log_dir.glob(f"cfst*.log"):
        try:
            old_log.unlink()
            print(f"{Color.YELLOW}已清理旧日志: {old_log}{Color.RESET}")
        except Exception as e:
            print(f"{Color.RED}日志清理失败: {old_log} - {str(e)}{Color.RESET}")

    # 配置日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 移除已有的日志处理器
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # 创建文件处理器（按时间戳命名）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(log_dir / f"cfst_{timestamp}.log", encoding='utf-8')
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    
    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# ---------------------------- 核心类 ----------------------------
class CFSpeedTester:
    """Cloudflare 测速操作器（支持多协议类型）"""
    
    def __init__(self, ip_type: str, args):
        """初始化测速器
        参数:
            ip_type: 协议类型 (ipv4/ipv6/proxy)
            args: 命令行参数
        """
        self.ip_type = ip_type
        self.args = args  # 存储命令行参数
        # 结果文件存储路径
        self.results_dir = RESULTS_DIR / ip_type
        self.speed_dir = SPEED_DIR / ip_type

        # 创建必要目录
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.speed_dir.mkdir(parents=True, exist_ok=True)

        # 新增自定义 IP 文件路径处理
        self.ip_file = Path(args.ip_file) if args.ip_file else BASE_DIR / f"{ip_type}.txt"
        
        # 验证文件是否存在
        if not self.ip_file.exists():
            raise FileNotFoundError(f"IP 列表文件不存在: {self.ip_file}")

    def _get_cfst_binary(self) -> Path:
        """获取对应平台的CFST测速二进制文件
        返回:
            Path: 二进制文件路径
        异常:
            RuntimeError: 不支持的CPU架构
            FileNotFoundError: 二进制文件不存在
        """
        current_arch = platform.machine()  # 获取系统架构
        cfst_arch = ARCH_MAP.get(current_arch)
        if not cfst_arch:
            raise RuntimeError(f"不支持的架构: {current_arch}")
        
        # 构建二进制文件路径
        cfst_path = BASE_DIR / cfst_arch / "cfst"
        if not cfst_path.exists():
            raise FileNotFoundError(f"CFST二进制文件缺失: {cfst_path}")
        return cfst_path

    def execute_tests(self):
        """执行多地区码测试流程
        返回:
            int: 成功测试的地区码数量
        """
        success_count = 0
        for cfcolo in CFCOLO_LIST:
            if self._test_single_colo(cfcolo):
                success_count += 1
        return success_count

    def _test_single_colo(self, cfcolo: str) -> bool:
        """单个地区码测试流程
        参数:
            cfcolo: 地区码 (如HKG)
        返回:
            bool: 是否成功完成测试
        """
        try:
            # 随机选择测试端口
            port = random.choice(CLOUDFLARE_PORTS)
            # 生成结果文件路径
            result_file = self._generate_result_path(cfcolo)
            result_file.touch()  # 创建空文件标记开始
            
            # 执行测速测试（传递allip参数）
            if not self._run_cfst_test(cfcolo, port, result_file, self.args.allip):

                self._clean_all_colo_files(cfcolo)
                return False

            # 检查结果文件有效性
            if result_file.stat().st_size == 0:
                logging.warning(f"{Color.YELLOW}结果文件为空，删除: {result_file}{Color.RESET}")
                result_file.unlink()
                return False
    
            # 处理测速结果
            processed_entries = self._process_results(result_file, cfcolo, port)
            if not processed_entries:
                self._clean_all_colo_files(cfcolo)
                return False
    
            # 清理旧文件（保留当前）
            self._clean_old_files_except_current(cfcolo, result_file)
            
            # DNS更新流程
            if result_file.exists() and result_file.stat().st_size > 0:
                try:
                    subprocess.run(
                        [sys.executable, "-u", "ddns.py", "-t", self.ip_type, "--colos", cfcolo],
                        check=True
                    )
                except subprocess.CalledProcessError as e:
                    logging.error(f"{Color.RED}DNS更新失败: {cfcolo} - {str(e)}{Color.RESET}")
            else:
                logging.warning(f"{Color.YELLOW}跳过DNS更新: {result_file} 为空或不存在{Color.RESET}")
    
            return True
        except Exception as e:
            self._clean_all_colo_files(cfcolo)
            logging.error(f"{Color.RED}{cfcolo} 测试失败: {str(e)}{Color.RESET}")
            return False

    def _run_cfst_test(self, cfcolo: str, port: int, result_file: Path, allip: bool = False) -> bool:
        """执行CFST测速命令
        参数:
            cfcolo: 地区码
            port: 测试端口
            result_file: 结果文件路径
            allip: 是否使用-allip参数
        返回:
            bool: 命令是否执行成功
        """
        cfst_path = self._get_cfst_binary()
        ip_file = BASE_DIR / f"{self.ip_type}.txt"  # IP列表文件
    
        # 构建命令参数
        cmd = [
            str(cfst_path),
            "-f", str(self.ip_file),  # 修改此处使用实例变量
            "-o", str(result_file),
            "-url", "https://cloudflare.cdn.openbsd.org/pub/OpenBSD/7.3/src.tar.gz",  # 测速文件URL
            "-cfcolo", cfcolo,
            "-tl", str(DEFAULT_PARAMS["tl"]),   # 平均延迟上限
            "-tll", str(DEFAULT_PARAMS["tll"]), # 平均延迟下限
            "-tlr", str(DEFAULT_PARAMS["tlr"]), # 丢包率阈值
            "-n", str(DEFAULT_PARAMS["n"]),     # 测速线程数
            "-tp", str(port),                   # 测试端口
            "-dn", str(DEFAULT_PARAMS["dn"]),   # 下载测速数量
            "-p", str(DEFAULT_PARAMS["p"]),     # 显示结果数量
            "-httping"                          # 启用HTTPing测试
        ]
        
        # 根据参数添加-allip选项
        if allip:
            cmd.append("-allip")
    
        try:
            logging.info(f"{Color.CYAN}正在测试 {cfcolo} (端口: {port})...{Color.RESET}")
            # 执行测速命令
            subprocess.run(cmd, check=True, stdout=sys.stdout, stderr=sys.stderr)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"{Color.RED}命令执行失败: {str(e)}{Color.RESET}")
            return False

    def _process_results(self, result_file: Path, cfcolo: str, port: int) -> list:
        """处理测速结果并生成节点信息
        参数:
            result_file: 原始结果文件路径
            cfcolo: 地区码
            port: 测试端口
        返回:
            list: 处理后的条目列表
        """
        entries = []
        # 获取地区码对应的表情符号和国家代码
        emoji_data = colo_emojis.get(cfcolo, ("", "US"))
        emoji, country_code = emoji_data[0], emoji_data[1]

        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ip = row.get('IP 地址', '').strip()
                    speed = row.get('下载速度 (MB/s)', '0').strip()

                    # 校验数据有效性
                    if not ip or not speed:
                        continue

                    # 构造结果条目
                    try:
                        speed_float = float(speed)
                        entry = {
                            "ip": ip,
                            "port": port,
                            "speed": speed_float,
                            "emoji": emoji,
                            "colo": cfcolo,
                            "country": country_code,
                            "timestamp": datetime.now().isoformat()
                        }
                        entries.append(entry)
                    except ValueError:
                        continue

            # 按速度排序取前5名
            sorted_entries = sorted(entries, key=lambda x: x["speed"], reverse=True)[:5]
            self._save_processed_results(cfcolo, sorted_entries)
            return sorted_entries

        except Exception as e:
            logging.error(f"{Color.RED}结果处理失败: {str(e)}{Color.RESET}")
            return []

    def _generate_result_path(self, cfcolo: str) -> Path:
        """生成结果文件路径（包含时间戳）
        参数:
            cfcolo: 地区码
        返回:
            Path: 结果文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.results_dir / f"{cfcolo}_{timestamp}.csv"

    def _save_processed_results(self, cfcolo: str, entries: list):
        """保存处理后的结果到JSON和文本文件
        参数:
            cfcolo: 地区码
            entries: 处理后的条目列表
        """
        if not entries:
            logging.warning(f"{Color.YELLOW}无有效数据，跳过生成文件{Color.RESET}")
            return
    
        # 保存JSON格式结果
        json_file = self.speed_dir / f"{cfcolo}.json"
        with open(json_file, 'w', encoding='utf-8') as f_json:
            json.dump(entries, f_json, ensure_ascii=False, indent=2)
        logging.info(f"{Color.GREEN}已保存最佳结果到: {json_file}{Color.RESET}")
    
        # 生成易读的文本格式结果
        txt_file = self.speed_dir / f"{cfcolo}.txt"
        with open(txt_file, 'w', encoding='utf-8') as f_txt:
            for entry in entries:
                ip = entry['ip']
                # IPv6地址需要加方括号
                if self.ip_type == 'ipv6':
                    ip = f"[{ip}]"
                port = entry['port']
                # 速度显示格式处理
                speed_str = f"┃⚡{entry['speed']:.2f}MB/s" if entry['speed'] > 0 else ""
                line = f"{ip}:{port}#{entry['emoji']}{entry['country']}{speed_str}\n"
                
                # 控制台彩色输出
                full_line = line.strip()
                print(
                    f"{Color.CYAN}[写入{cfcolo}.txt]{Style.RESET_ALL} "
                    f"{Fore.WHITE}{full_line.split('#')[0]}{Style.RESET_ALL}"
                    f"{Fore.YELLOW}#{full_line.split('#')[1]}{Style.RESET_ALL}"
                )
                logging.info(f"[写入{cfcolo}.txt] {full_line}")
                
                f_txt.write(line)
        logging.info(f"{Color.GREEN}已生成节点信息文件: {txt_file}{Color.RESET}")

    def _clean_all_colo_files(self, cfcolo: str):
        """清理指定地区码的所有相关文件
        参数:
            cfcolo: 地区码
        """
        # 清理results目录中的CSV文件
        patterns = [f"{cfcolo}_*.csv"]
        for pattern in patterns:
            for old_file in self.results_dir.glob(pattern):
                try:
                    old_file.unlink()
                    logging.info(f"{Color.YELLOW}已清理文件: {old_file}{Color.RESET}")
                except Exception as e:
                    logging.error(f"{Color.RED}清理失败: {old_file} - {str(e)}{Color.RESET}")

    def _clean_old_files_except_current(self, cfcolo: str, current_file: Path):
        """清理旧文件（保留当前文件）
        参数:
            cfcolo: 地区码
            current_file: 当前结果文件路径
        """
        # 清理results目录中的旧CSV文件
        patterns = [f"{cfcolo}_*.csv"]
        for pattern in patterns:
            for old_file in self.results_dir.glob(pattern):
                if old_file != current_file:
                    try:
                        old_file.unlink()
                        logging.info(f"{Color.YELLOW}已清理旧文件: {old_file}{Color.RESET}")
                    except Exception as e:
                        logging.error(f"{Color.RED}清理失败: {old_file} - {str(e)}{Color.RESET}")

    # ---------------------------- Git提交功能 ----------------------------
    @staticmethod
    def git_commit_and_push(ip_type: str):
        """提交结果到Git仓库
        参数:
            ip_type: 协议类型
        返回:
            bool: 是否提交成功
        """
        try:
            # 检查是否有文件变更
            status_check = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                check=True
            )
            if not status_check.stdout.strip():
                logging.info(f"{Color.YELLOW}无文件变更，跳过Git提交{Color.RESET}")
                return False
    
            # 添加所有变更文件
            subprocess.run(["git", "add", "."], cwd=BASE_DIR, check=True)
            
            # 构造提交信息
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"Update {ip_type} speed results - {timestamp}"
            
            # 提交变更
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=BASE_DIR, check=True)
            
            # 强制推送到远程仓库
            subprocess.run(["git", "push", "-f"], cwd=BASE_DIR, check=True)
            
            logging.info(f"{Color.GREEN}Git提交成功: {commit_msg}{Color.RESET}")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"{Color.RED}Git操作失败: {str(e)}{Color.RESET}")
            return False
        except Exception as e:
            logging.error(f"{Color.RED}Git提交异常: {str(e)}{Color.RESET}")
            return False

# ---------------------------- 主程序 ----------------------------
def parse_arguments():
    """解析命令行参数
    返回:
        argparse.Namespace: 解析后的参数对象
    """
    parser = argparse.ArgumentParser(description="Cloudflare Speed Test 自动化脚本")
    parser.add_argument("-t", "--type", required=True, choices=["ipv4", "ipv6", "proxy"],
                        help="测试协议类型")
    parser.add_argument("-c", "--colos", default="HKG,LAX,NRT,SIN,FRA,ICN,AMS",
                        help="逗号分隔的colo地区码列表")
    parser.add_argument("-a", "--allip", action="store_true",
                        help="测速全部的IP（添加-allip参数到cfst命令）")
    parser.add_argument("--git-commit", action="store_true",
                        help="测试完成后提交结果到Git仓库")
    parser.add_argument("--ip-file", type=str, 
                      help="自定义IP列表文件路径（覆盖默认的 ip_type.txt）",
                      default=None)
    return parser.parse_args()

def main():
    """主执行流程
    返回:
        int: 退出码（0成功，1失败）
    """
    args = parse_arguments()
    # 处理地区码参数
    selected_colos = [c.strip().upper() for c in args.colos.split(',')] if args.colos else CFCOLO_LIST
    success_count = 0
    error_message = None
    git_success = False
    failed_colos = []
    success_colos = []  # 记录成功的地区码

    try:
        # 初始化日志系统
        setup_logging(args.type)
        logging.info(f"{Color.BOLD}启动 {args.type.upper()} 测试{Color.RESET}")
        
        # 发送开始通知到Telegram
        start_msg = f"🚀 开始 {args.type.upper()} 测试，地区码: {', '.join(selected_colos)}"
        send_message_with_fallback(
            worker_url=os.getenv("CF_WORKER_URL"),
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            message=start_msg,
            secret_token=os.getenv("SECRET_TOKEN")
        )

        # 初始化测速器并执行测试
        tester = CFSpeedTester(args.type, args)
        for cfcolo in selected_colos:
            if tester._test_single_colo(cfcolo):
                success_count += 1
                success_colos.append(cfcolo)
            else:
                failed_colos.append(cfcolo)
                print(f"{Fore.RED}❌ {cfcolo} 测试失败{Style.RESET_ALL}")

        # 执行Git提交（如果启用）
        if args.git_commit and success_count > 0:
            logging.info(f"{Color.CYAN}正在提交结果到Git仓库...{Color.RESET}")
            git_success = CFSpeedTester.git_commit_and_push(args.type)

        # 构造状态消息
        timestamp = datetime.now().strftime("%m/%d %H:%M")
        ddns_triggered = success_count > 0
        status_msg = [
            f"🌐 CFST更新维护 - {timestamp}",
            "├─ 更新区域",
            f"│  ├─ 类型: {args.type.upper()}",
            f"│  ├─ ✅ 成功({success_count}/{len(selected_colos)}): {', '.join(success_colos) if success_colos else '无'}",
            f"│  └─ ❌ 失败({len(failed_colos)}/{len(selected_colos)}): {', '.join(failed_colos) if failed_colos else '无'}",
            "└─ 自动维护",
            f"   └─ {'⚡ 已触发DDNS更新' if ddns_triggered else '🛠️ 无可用更新'}"
        ]

    except Exception as e:
        error_message = f"❌ {args.type.upper()} 测试异常: {str(e)}"
        logging.error(f"{Color.RED}{error_message}{Color.RESET}", exc_info=True)
        status_msg = [error_message]
        return 1
        
    finally:
        # 确保状态消息已定义
        if 'status_msg' not in locals():
            status_msg = [f"🌐 CFST更新维护 - 未完成测试（严重错误）"]

        # 发送最终通知
        try:
            send_message_with_fallback(
                worker_url=os.getenv("CF_WORKER_URL"),
                bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
                chat_id=os.getenv("TELEGRAM_CHAT_ID"),
                message="\n".join(status_msg),
                secret_token=os.getenv("SECRET_TOKEN")
            )
        except Exception as e:
            logging.error(f"{Color.RED}Telegram 通知发送失败: {str(e)}{Color.RESET}")
        
        # 输出最终结果
        logging.info(f"{Color.CYAN}=== 测试流程结束 ==={Color.RESET}")
        if failed_colos:
            print(f"\n{Fore.RED}=== 失败地区码 ==={Style.RESET_ALL}")
            for colo in failed_colos:
                print(f"{Fore.YELLOW}• {colo}{Style.RESET_ALL}")

        return 0 if success_count > 0 else 1

if __name__ == "__main__":
    sys.exit(main())

# ---------------------------- 单元测试 ----------------------------
class TestCFSpeedTester(unittest.TestCase):
    """CFSpeedTester 单元测试套件"""

    def setUp(self):
        """初始化测试环境"""
        self.tester = CFSpeedTester("ipv4")
        self.test_colo = "HKG"

    def test_binary_path(self):
        """测试二进制文件路径检测"""
        path = self.tester._get_cfst_binary()
        self.assertTrue(path.exists(), "二进制文件路径不存在")

    def test_result_processing(self):
        """测试结果处理逻辑"""
        test_file = Path(__file__).parent / "test_data.csv"
        processed = self.tester._process_results(test_file, self.test_colo, 443)
        self.assertGreaterEqual(len(processed), 1, "应该至少处理一个有效结果")

    @patch('subprocess.run')
    def test_cfst_execution(self, mock_run):
        """测试CFST命令执行模拟"""
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout='', stderr='')
        result = self.tester._run_cfst_test(self.test_colo, 443, Path("/tmp/test.csv"))
        self.assertTrue(result, "命令应该执行成功")

if __name__ == '__main__':
    unittest.main()
