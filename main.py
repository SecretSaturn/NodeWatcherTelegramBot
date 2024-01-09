import asyncio
import aiohttp
from datetime import datetime, timezone
import dateutil.parser
from dotenv import load_dotenv
import os
from telegram import Update
from telegram.ext import CommandHandler, CallbackContext, ApplicationBuilder, Updater, filters, MessageHandler
import logging
import threading

# Read URLs from file
def read_urls(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    return ["http://" + line.strip() + "/status?" for line in lines]


# Load configuration from .env file
load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
channel_id = os.getenv('CHANNEL_ID')
file_path = os.getenv('FILE_PATH')
urls = read_urls(file_path)
time_before_fallen_behind = int(os.getenv('TIME_BEFORE_FALLEN_BEHIND'))
update_time = int(os.getenv('UPDATE_TIME'))

# Function to check nodes
async def check_nodes(urls, report_all=False):
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
                        if report_all: 
                            message = f"Node {node_counter}, IP: ..XXX.{anonymized_url}, Block {latest_block_height}, Time {formatted_block_time}, Δ: {delta_to_now.seconds} s  {status}"
                            status_messages.append(message)
                    else:
                        status = "❌"
                        broken_nodes += 1
                        message = f"Node {node_counter}, IP: ..XXX.{anonymized_url}, Block {latest_block_height}, Time {formatted_block_time}, Δ: {delta_to_now.seconds} s  {status}"
                        status_messages.append(message)
        except Exception as e:
            error_message = f"Node {node_counter}, unreachable: ..XXX.{anonymized_url} ❌"
            status_messages.append(error_message)
            broken_nodes += 1
    if report_all or broken_nodes > 0:
        percentage_good_nodes = (good_nodes / node_counter) * 100 if node_counter > 0 else 0
        summary_message = f"\n*Nodes Summary: {good_nodes}/{node_counter} ✅ ({percentage_good_nodes:.2f}%)*"
        status_messages.append(summary_message)
        combined_message = '\n'.join(status_messages)
        return combined_message
    return None


# Command handler for /status, modified for user-specific URLs
async def status(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    message = await check_nodes(urls, True)
    if message:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode="markdown")
        # Command handler for /status, modified for user-specific URLs

async def start(update: Update, context: CallbackContext):
    try:
        chat_id =  update.effective_chat.id
        logging.info(f"User ID: {chat_id}")  # Log the user ID for debugging

        time_before_fallen_behind_str = str(time_before_fallen_behind).replace("_", "\\_")
        message = ("Usage: \n Use /status to get a complete status update once. \n Use /autoreport to get all faulty nodes, automatically checks every " + 
                   time_before_fallen_behind_str + "s. ")
        if message:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode="markdown")
    except Exception as e:
        logging.error(f"Error in start function: {e}")

# Global dictionary to keep track of users and their associated threads
user_threads = {}

async def auto_report_for_user(chat_id):
    while True:
        message = await check_nodes(urls, False)
        if message:
            result = await ApplicationBuilder().token(bot_token).build().bot.send_message(chat_id=chat_id, text=message, parse_mode="markdown")
        await asyncio.sleep(update_time)

def start_periodic_task_for_user(chat_id):
    async def task():
        await auto_report_for_user(chat_id)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(task())

async def handle_message(update: Update, context: CallbackContext):
    bot_username = context.bot.username
    message_text = update.effective_message.text
    chat_id = update.effective_message.chat_id

  # Check for "/start" command
    if f"@{bot_username}" in message_text and "/start" in message_text:
        await start(update,context)

    # Check for "/autoreport" command
    elif f"@{bot_username}" in message_text and "/autoreport" in message_text:
        await autoreport(update,context)

    # Check for "/status" command
    elif f"@{bot_username}" in message_text and "/status" in message_text:
        await status(update,context)

async def autoreport(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id not in user_threads:
        thread = threading.Thread(target=start_periodic_task_for_user, args=(chat_id,))
        thread.start()
        user_threads[chat_id] = thread
        await context.bot.send_message(chat_id=chat_id, text="Auto-reporting started.")
    else:
        await context.bot.send_message(chat_id=chat_id, text="You are already subscribed to auto-reporting.")

def main():
    application = ApplicationBuilder().token(bot_token).build()
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('autoreport', autoreport))
    message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    application.add_handler(message_handler)

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()