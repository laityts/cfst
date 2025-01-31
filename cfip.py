import requests
from bs4 import BeautifulSoup
import re
import os
import logging
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from colo_emojis import colo_emojis  # 确保colo_emojis.py存在并正确导出字典

# 确保日志目录存在
os.makedirs('logs', exist_ok=True)

# 配置日志记录
logging.basicConfig(
    filename='logs/error.log',  # 日志文件路径
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 目标网页URL
url = 'https://ip.164746.xyz/'

# 设置请求头模拟浏览器访问
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}

# 创建Session对象并配置重试策略
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

# 发送GET请求获取网页内容
response = session.get(url, headers=headers)
response.encoding = 'utf-8'  # 设置编码为UTF-8

# 使用BeautifulSoup解析HTML内容
soup = BeautifulSoup(response.text, 'html.parser')

# 定位表格
table = soup.find('table')
if not table:
    print("未找到表格")
    exit()

# 定位表格主体
tbody = table.find('tbody')
if not tbody:
    print("表格中缺少tbody")
    exit()

# 提取所有行
rows = tbody.find_all('tr')

# 存储提取的数据
data = []
for row in rows:
    tds = row.find_all('td')
    if len(tds) < 7:
        continue
    ip_tag = tds[0].find('a')
    if not ip_tag:
        continue  # 跳过没有链接的行
    ip = ip_tag.get_text(strip=True)
    avg_latency = tds[4].get_text(strip=True)
    download_speed = tds[5].get_text(strip=True)
    data.append({
        'ip': ip,
        'avg_latency': avg_latency,
        'download_speed': download_speed
    })

# 处理每个IP获取colo信息并准备写入内容
lines = []
for entry in data:
    ip = entry['ip']
    download_speed = entry['download_speed']
    try:
        trace_url = f'http://{ip}/cdn-cgi/trace'
        # 使用Session对象发送请求
        response = session.get(trace_url, headers=headers, timeout=10)
        response.raise_for_status()  # 检查HTTP错误状态
        trace_text = response.text
        
        # 打印Trace API的返回内容
        print(f"Trace API返回内容: {trace_text}")

        # 使用正则表达式提取colo字段
        colo_match = re.search(r'colo=(\w+)', trace_text)
        if colo_match:
            colo = colo_match.group(1)
            # 从colo_emojis字典获取Emoji，默认值为未知
            emoji = colo_emojis.get(colo, '☁️')  # 默认使用地球Emoji
            line = f"{ip}#{emoji}{colo}┃⚡{download_speed}\n"
            lines.append(line)
            print(f"成功提取colo: {colo}, Emoji: {emoji}, 数据: {line.strip()}")
        else:
            print(f"IP {ip} 的Trace信息中未找到colo字段")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 503:
            print(f"IP {ip} 的Trace API暂时不可用: {e}")
            logging.error(f"IP {ip} 的Trace API暂时不可用: {e}")
        else:
            print(f"请求IP {ip} 的Trace API失败: {e}")
            logging.error(f"请求IP {ip} 的Trace API失败: {e}")
    except requests.exceptions.RequestException as e:
        print(f"请求IP {ip} 的Trace API失败: {e}")
        logging.error(f"请求IP {ip} 的Trace API失败: {e}")
    except Exception as e:
        print(f"处理IP {ip} 时发生错误: {e}")
        logging.error(f"处理IP {ip} 时发生错误: {e}")

# 确保输出目录存在
os.makedirs('speed', exist_ok=True)

# 打印即将写入的数据
print("即将写入的数据：")
for line in lines:
    print(line.strip())

# 将结果写入文件
with open('speed/cfip.txt', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("处理完成，结果已写入 speed/cfip.txt")