import logging
import re
import csv
import subprocess
import sys
from pathlib import Path
from telethon.sync import TelegramClient
from telethon.tl.types import DocumentAttributeFilename
import socks
from colo_emojis import colo_emojis  # 导入数据中心emoji映射
from checker import process_ip_list
from dotenv import load_dotenv  # 导入 dotenv
import os  # 导入 os 模块以读取环境变量

# 加载 .env 文件
load_dotenv()

# --------------------------
# 配置区（从 .env 文件中读取）
# --------------------------
API_ID = int(os.getenv('API_ID'))  # 从 .env 文件中读取 API_ID
API_HASH = os.getenv('API_HASH')  # 从 .env 文件中读取 API_HASH
CHANNEL = '@cloudflareorg'
LIMIT = 10
DOWNLOAD_DIR = 'csv'
OUTPUT_FILE = 'cfip/cfip.txt'
LOG_FILE= 'logs/cfiplog.txt'
Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
Path("cfip").mkdir(exist_ok=True)

# 代理配置（可选）
PROXY_TYPE = 'socks5'
PROXY_HOST = ''
PROXY_PORT = ''
PROXY_USER = ''
PROXY_PASS = ''

logging.basicConfig(
    format='%(asctime)s - %(levelname)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def delete_old_csv_files():
    """删除所有 45102*.csv 文件"""
    csv_files = Path(DOWNLOAD_DIR).glob("45102*.csv")
    for file in csv_files:
        try:
            file.unlink()
            logger.info(f"已删除旧文件: {file}")
        except Exception as e:
            logger.error(f"删除文件失败: {file} - {e}")

def is_target_file(filename: str) -> bool:
    """检查是否是 45102 开头的 CSV 文件"""
    return bool(re.match(r'^45102.*\.csv$', filename, re.IGNORECASE)) if filename else False

def get_proxy_config():
    if not PROXY_TYPE or not PROXY_HOST:
        return None

    proxy_map = {
        'socks5': socks.SOCKS5,
        'http': socks.HTTP
    }
    if PROXY_TYPE not in proxy_map:
        raise ValueError(f"不支持的代理类型: {PROXY_TYPE}")

    return (
        proxy_map[PROXY_TYPE],
        PROXY_HOST,
        PROXY_PORT,
        True,
        PROXY_USER if PROXY_USER else None,
        PROXY_PASS if PROXY_PASS else None
    )

def extract_data_from_csv(csv_file):
    """解析 CSV 文件并格式化数据"""
    extracted_data = []

    with open(csv_file, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # 打印表头，检查 CSV 文件的字段名是否正确
        logger.info(f"CSV 表头: {reader.fieldnames}")
                
        for row in reader:
            try:
                logger.info(f"读取的行: {row}")  # 打印每一行的数据
                
                ip = row.get('IP地址', '').strip()
                port = row.get('端口', '443').strip()
                colo_code = row.get('数据中心', '').strip()
                speed = row.get('下载速度', '未知').strip()

                if not ip or not colo_code:
                    continue  # 跳过无效行

                # 获取数据中心对应的emoji
                emoji = colo_emojis.get(colo_code, '')
                # 格式化数据行
                data_line = f"{ip}:{port}#{emoji}{colo_code}"
                extracted_data.append(data_line)
                logger.info(data_line)  # 打印到终端

            except Exception as e:
                logger.error(f"解析 CSV 行失败: {e}")

    return extracted_data

def save_results(data, output_file):
    """保存提取结果到文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(data))
    logger.info(f"提取数据已保存到: {output_file}")

def git_commit_and_push(commit_message="Update CSV file"):
    """执行 git commit 和 push 操作"""
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
        logger.info("已将文件上传到 GitHub 仓库。")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git 操作失败: {e}")
        sys.exit(1)

def main():
    delete_old_csv_files()
    
    proxy = get_proxy_config()
    
    with TelegramClient('session_name', API_ID, API_HASH, proxy=proxy) as client:
        try:
            channel = client.get_entity(CHANNEL)
            logger.info(f"成功连接频道: {channel.title}")

            file_found = False

            for message in client.iter_messages(channel, limit=LIMIT):
                try:
                    if not (message.media and message.document):
                        continue

                    filename = next(
                        (attr.file_name for attr in message.document.attributes 
                         if isinstance(attr, DocumentAttributeFilename)),
                        None
                    )

                    if not is_target_file(filename):
                        continue

                    save_path = Path(DOWNLOAD_DIR) / filename

                    if save_path.exists():
                        logger.warning(f"文件已存在，跳过: {filename}")
                        continue

                    logger.info(f"发现最新文件: {filename}")
                    client.download_media(
                        message,
                        file=save_path,
                        progress_callback=lambda cur, tot: logger.info(
                            f"下载进度: {cur/tot:.1%} - {filename}"
                        )
                    )
                    logger.info(f"文件已保存到: {save_path}")
                    file_found = True

                    # 解析 CSV 并保存结果
                    extracted_data = extract_data_from_csv(save_path)
                    save_results(extracted_data, OUTPUT_FILE)

                    break  # 下载完成后立即中断循环

                except Exception as e:
                    logger.error(f"处理消息 {message.id} 失败: {str(e)}")
                    continue

            if not file_found:
                logger.warning(f"前 {LIMIT} 条消息中未找到符合条件的文件，请尝试增大 LIMIT 值")

        except Exception as e:
            logger.error(f"程序运行失败: {str(e)}")
            raise

    # 删除不可达的 IP
    process_ip_list(OUTPUT_FILE,LOG_FILE)
    
    # Git 上传步骤
    git_commit_and_push("自动更新文件")

if __name__ == '__main__':
    main()