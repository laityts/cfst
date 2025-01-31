import os
import subprocess
import csv
import sys
import requests
import random
import logging
import platform
from colo_emojis import colo_emojis
from checker import process_ip_list

# ------------------------------
# 初始化设置
# ------------------------------

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/fdlog.txt"),  # 日志写入文件
        logging.StreamHandler(sys.stdout)      # 日志输出到控制台
    ]
)
logging = logging.getLogger(__name__)

def install_package(package_name):
    """检查并安装指定的Python包"""
    try:
        __import__(package_name)
        logging.info(f"{package_name} 已安装")
    except ImportError:
        logging.info(f"{package_name} 未安装，正在安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            logging.info(f"{package_name} 安装成功")
        except subprocess.CalledProcessError as e:
            logging.error(f"安装 {package_name} 失败: {e}")
            sys.exit(1)

# 检查并安装所需的库
required_packages = ["requests", "csv"]
for package in required_packages:
    install_package(package)

# 获取当前脚本的路径
script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

# 切换到当前脚本所在的目录
os.chdir(script_dir)

# 工具函数
def remove_file(file_path):
    """删除指定路径的文件"""
    if os.path.exists(file_path):
        os.remove(file_path)
        logging.info(f"已删除 {file_path} 文件。")

def create_directories(directories):
    """创建所需的目录"""
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logging.info(f"已创建或确认目录 {directory} 存在。")

def download_file(url, file_path):
    """从指定 URL 下载文件"""
    try:
        logging.info(f"正在从 {url} 下载文件...")
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(file_path, "wb") as file:
                file.write(response.content)
            logging.info(f"已成功下载 {file_path} 文件。")
        else:
            logging.error(f"下载 {file_path} 文件失败，状态码: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"下载 {file_path} 文件时发生错误: {e}")
        sys.exit(1)

def execute_git_pull():
    """执行 git pull 操作"""
    try:
        logging.info("正在执行 git pull...")
        subprocess.run(["git", "pull"], check=True)
        logging.info("git pull 成功，本地仓库已更新。")
    except subprocess.CalledProcessError as e:
        logging.error(f"git pull 失败: {e}")
        sys.exit(1)

def download_and_extract(url, target_path):
    """下载并解压文件"""
    downloaded_file = url.split("/")[-1]
    logging.info(f"正在下载文件: {downloaded_file}")
    subprocess.run(["wget", "-N", url], check=True)
    
    if downloaded_file.endswith(".tar.gz"):
        try:
            subprocess.run(["tar", "-zxf", downloaded_file], check=True)
            logging.info(f"已成功解压: {downloaded_file}")
        except subprocess.CalledProcessError as e:
            logging.error(f"解压失败: {e}")
            sys.exit(1)
    elif downloaded_file.endswith(".zip"):
        try:
            subprocess.run(["unzip", downloaded_file], check=True)
            logging.info(f"已成功解压: {downloaded_file}")
        except subprocess.CalledProcessError as e:
            logging.error(f"解压失败: {e}")
            sys.exit(1)
    else:
        logging.error("无法识别的压缩文件格式！")
        sys.exit(1)
    
    remove_file(downloaded_file)
    subprocess.run(["mv", "CloudflareST", target_path], check=True)
    subprocess.run(["chmod", "+x", target_path], check=True)

def write_to_file(file_path, data, mode="a"):
    """将数据写入文件"""
    with open(file_path, mode=mode, encoding="utf-8") as file:
        for item in data:
            file.write(item + "\n")
            logging.info(f"写入: {item}")

def read_csv(file_path):
    """读取CSV文件并返回数据"""
    if os.path.getsize(file_path) == 0:
        logging.warning(f"文件 {file_path} 为空，跳过读取。")
        return None, None
    
    with open(file_path, mode="r", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        try:
            header = next(reader)  # 读取表头
        except StopIteration:
            logging.warning(f"文件 {file_path} 格式不正确或为空，跳过读取。")
            return None, None
        
        if "下载速度 (MB/s)" not in header:
            logging.error("无法找到下载速度列，请检查 CSV 文件表头。")
            sys.exit(1)
        
        speed_index = header.index("下载速度 (MB/s)")
        ip_addresses = []
        download_speeds = []
        
        for row in reader:
            ip_addresses.append(row[0])
            download_speeds.append(row[speed_index])
            if len(ip_addresses) >= 10:  # 读取csv文件前十行
                break
        
        return ip_addresses, download_speeds

def execute_cfst_test(cfst_path, cfcolo, result_file, random_port):
    """执行 CloudflareSpeedTest 测试"""
    logging.info(f"正在测试区域: {cfcolo}")
    
    # 执行 CloudflareSpeedTest 测试
    try:
        subprocess.run(
            [
                f"./{cfst_path}",
                "-f", "proxy.txt",
                "-o", result_file,
                "-httping",
                "-cfcolo", cfcolo,
                "-tl", "300",
                "-tll", "10",
                "-tp", str(random_port),
                "-dn", "10",
                "-p", "10"
            ],
            check=True
        )
    except subprocess.CalledProcessError as e:
        logging.error(f"CloudflareSpeedTest 测试失败: {e}")
        sys.exit(1)
    
    # 检查是否生成了 result_file 文件
    if not os.path.exists(result_file):
        logging.warning(f"未生成 {result_file} 文件，正在新建一个空的 {result_file} 文件。")
        with open(result_file, "w") as file:
            file.write("")  # 创建一个空文件
        logging.info(f"已新建 {result_file} 文件。")
    else:
        logging.info(f"{result_file} 文件已存在，无需新建。")

def process_test_results(cfcolo, result_file, output_txt, port_txt, output_cf_txt, random_port):
    """处理测试结果并写入文件"""
    ip_addresses, download_speeds = read_csv(result_file)
    
    if not ip_addresses:
        return  # 跳过当前循环

    logging.info(f"区域 {cfcolo} 提取到的 IP 地址数量: {len(ip_addresses)}")
    
    # 将 IP 地址和 colo 信息写入 fd.txt
    write_to_file(output_txt, [f"{ip}#{colo_emojis.get(cfcolo, '☁️')}{cfcolo}" for ip in ip_addresses])
    logging.info(f"提取的 IP 地址和 colo 信息已保存到 {output_txt}")
    
    # 将 IP 地址、端口、colo 信息和下载速度写入 fdport.txt
    write_to_file(port_txt, [f"{ip}:{random_port}#{colo_emojis.get(cfcolo, '☁️')}{cfcolo}┃⚡{speed}(MB/s)" for ip, speed in zip(ip_addresses, download_speeds)])
    logging.info(f"IP 地址、端口、colo 信息和下载速度已追加到 {port_txt}")
    
    # 清空 result.csv 文件
    open(result_file, "w").close()
    logging.info(f"已清空 {result_file} 文件。")

def git_commit_and_push(commit_message):
    """执行 git commit 和 push 操作"""
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
        logging.info("已将文件上传到 GitHub 仓库。")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git 操作失败: {e}")
        sys.exit(1)

# 在脚本执行前删除文件
files_to_remove = ["cfip/fd.txt", "logs/fdlog.txt", "port/fdport.txt"]
for file_path in files_to_remove:
    remove_file(file_path)

# 创建所需的目录
directories_to_create = ["csv", "log", "port", "cfip", "speed"]
create_directories(directories_to_create)

# 定义文件路径和变量
cfst_path = "cfst"
result_file = "csv/resultfd.csv"
cfip_file = "cfip/fd.txt"
output_txt = "cfip/fd.txt"
port_txt = "port/fdport.txt"
log_file = "logs/fdlog.txt"
output_cf_txt = "speed/fd.txt"
proxy = "proxy.txt"
proxy_txt = "cfip/proxy.txt"
iplog_file = "logs/fdlog2.txt"
commit_message = "Update result.csv and fd.txt"

# 定义 cfcolo 数组（目标区域）
cfcolo_list = ["HKG", "SJC", "SEA", "LAX", "FRA", "NRT", "SIN"]

# Cloudflare 支持的标准端口列表
cf_ports = [443]

# 获取系统架构
system_arch = platform.machine().lower()

# 根据系统架构选择对应的下载链接
if system_arch in ["x86_64", "amd64"]:
    download_url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.2.5/CloudflareST_linux_amd64.tar.gz"
    cfst_path = "amd64/cfst"
elif system_arch in ["aarch64", "arm64"]:
    download_url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.2.5/CloudflareST_linux_arm64.tar.gz"
    cfst_path = "arm64/cfst"
elif system_arch in ["armv7l", "armv6l"]:
    download_url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.2.5/CloudflareST_linux_armv7.tar.gz"
    cfst_path = "armv7/cfst"
else:
    logging.error(f"不支持的架构: {system_arch}")
    sys.exit(1)

logging.info(f"检测到系统架构为 {system_arch}，将下载对应的 CloudflareST 版本: {download_url}")

# 删除 proxy.txt 文件（如果存在）
remove_file(proxy)

# 从指定 URL 下载 proxy.txt 文件
proxy_url = "https://ipdb.api.030101.xyz/?type=proxy&down=true"
download_file(proxy_url, proxy)

# 在执行主程序逻辑之前，先执行 git pull
execute_git_pull()

# 检查 cfst 文件是否存在
if not os.path.exists(cfst_path):
    download_and_extract(download_url, cfst_path)

# 遍历 cfcolo_list 并依次执行测试
for cfcolo in cfcolo_list:
    random_port = random.choice(cf_ports)
    execute_cfst_test(cfst_path, cfcolo, result_file, random_port)
    process_test_results(cfcolo, result_file, output_txt, port_txt, output_cf_txt, random_port)

# 删除不可达的 IP
process_ip_list(cfip_file,iplog_file)

# Git 上传步骤
git_commit_and_push(commit_message)