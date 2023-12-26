import asyncio
import aiohttp
from telegram import Bot
from datetime import datetime, timezone
import dateutil.parser
from dotenv import load_dotenv
import os

# Load configuration from .env file
load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
channel_id = os.getenv('CHANNEL_ID')
file_path = os.getenv('FILE_PATH')
time_before_fallen_behind = int(os.getenv('TIME_BEFORE_FALLEN_BEHIND'))
update_time = int(os.getenv('UPDATE_TIME'))

# Initialize bot
bot = Bot(token=bot_token)

# Read URLs from file
async def read_urls(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    return ["http://" + line.strip() + "/status?" for line in lines]

async def check_nodes(urls):
    while True:
        status_messages = []
        node_counter = 0
        good_nodes = 0
        broken_nodes = 0
        for url in urls:
            node_counter += 1
            anonymized_url = url.split("/")[-2].split(":")[0].split(".")[-1]
            datetime_now = datetime.now(timezone.utc)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=0.5) as response:
                        data = await response.json()
                        latest_block_height = data['result']['sync_info']['latest_block_height']
                        latest_block_time = data['result']['sync_info']['latest_block_time']
                        block_time = dateutil.parser.parse(latest_block_time)
                        formatted_block_time = block_time.strftime("%Y-%m-%dT%H:%M:%S")
                        delta_to_now = datetime_now - block_time
                        if delta_to_now.seconds <= time_before_fallen_behind:
                            status = "✅"
                            good_nodes += 1
                        else:
                            status = "❌"
                            broken_nodes += 1
                        message = f"Node {node_counter}, IP: ..XXX.{anonymized_url}, Block {latest_block_height}, Time {formatted_block_time}, Δ: {delta_to_now.seconds} s  {status}"
                        print(message)
                        status_messages.append(message)
            except Exception as e:
                print(f"Error with {url}: {e}")
                error_message = f"Node {node_counter}, unreachable: ..XXX.{anonymized_url} ❌"
                print(error_message)
                status_messages.append(error_message)
                broken_nodes += 1
        percentage_good_nodes = (good_nodes / node_counter) * 100 if node_counter > 0 else 0
        summary_message = f"\n*Nodes Summary: {good_nodes}/{node_counter} ✅ ({percentage_good_nodes:.2f}%)*"
        print(summary_message)
        status_messages.append(summary_message)
        combined_message = '\n'.join(status_messages)
        await bot.send_message(chat_id=channel_id, text=combined_message, parse_mode= "markdown" )
        await asyncio.sleep(update_time)

# Main function
async def main():
    urls = await read_urls(file_path)
    await check_nodes(urls)

# Execute
if __name__ == "__main__":
    asyncio.run(main())