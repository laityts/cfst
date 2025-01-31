import requests
import os
import logging
from datetime import datetime

# 从 colo_emojis.py 导入 colo_emojis 字典
from colo_emojis import colo_emojis

# 配置日志
def setup_logging():
    # 创建日志目录
    log_dir = "logs"  # 日志文件夹名称改为 log
    os.makedirs(log_dir, exist_ok=True)

    # 日志文件名格式：YYYY-MM-DD.log
    log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),  # 写入日志文件
            logging.StreamHandler()         # 打印到控制台
        ]
    )

# 抓取 IPv6 地址
def fetch_ipv6_addresses(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # 检查请求是否成功
        # 假设网页内容是纯文本，每行一个 IPv6 地址
        ipv6_addresses = response.text.strip().split('\n')
        logging.info(f"Fetched {len(ipv6_addresses)} IPv6 addresses from {url}")
        return ipv6_addresses
    except Exception as e:
        logging.error(f"Error fetching IPv6 addresses: {e}")
        return []

# 获取 colo 信息
def get_colo(ipv6):
    url = f"http://[{ipv6}]/cdn-cgi/trace"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        trace_info = response.text
        # 从 trace 信息中提取 colo
        colo = None
        for line in trace_info.split('\n'):
            if line.startswith('colo='):
                colo = line.split('=')[1]
                break
        return colo
    except Exception as e:
        logging.error(f"Error fetching colo for {ipv6}: {e}")
        return None

# 处理 IPv6 地址
def process_ipv6_addresses(ipv6_addresses):
    processed_addresses = []
    for address in ipv6_addresses:
        if not address.strip():
            continue
        # 提取 IPv6 部分
        ipv6 = address.split('#')[0].strip('[]')
        # 获取 colo 信息
        colo = get_colo(ipv6)
        if colo:
            # 获取对应的 emoji
            emoji = colo_emojis.get(colo, "")
            # 在 # 后面插入 {emoji}{colo}┃
            processed_address = address.replace("#CMCC-IPV6", f"#{emoji}{colo}┃CMCC-IPV6")
            processed_addresses.append(processed_address)
            logging.info(f"Processed address: {processed_address}")
        else:
            processed_addresses.append(address)  # 如果无法获取 colo，保留原地址
            logging.warning(f"No colo found for {ipv6}, using original address: {address}")
    return processed_addresses

# 主函数
def main():
    # 设置日志
    setup_logging()
    logging.info("Script started.")

    # 抓取 IPv6 地址
    url = "https://addressesapi.090227.xyz/cmcc-ipv6"
    ipv6_addresses = fetch_ipv6_addresses(url)
    if not ipv6_addresses:
        logging.error("No IPv6 addresses fetched. Exiting.")
        return

    # 处理 IPv6 地址
    processed_addresses = process_ipv6_addresses(ipv6_addresses)

    # 确保输出目录存在
    output_dir = "cfip"
    os.makedirs(output_dir, exist_ok=True)

    # 将结果写入 cfip/cfipv6.txt
    output_file = os.path.join(output_dir, "cfipv6.txt")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            for address in processed_addresses:
                f.write(address + "\n")
        logging.info(f"Processed IPv6 addresses have been written to {output_file}")
    except Exception as e:
        logging.error(f"Error writing to {output_file}: {e}")

    logging.info("Script finished.")

if __name__ == "__main__":
    main()