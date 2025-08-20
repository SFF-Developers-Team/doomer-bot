import os, json, discord, datetime, re, aiohttp
from discord import *
from discord.ext import tasks
from dotenv import load_dotenv
from zandronumserver import ZandronumServer, RConServerUpdate
import asyncio
load_dotenv()

# Bot settings
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = str(os.getenv('DOOM_SERVER_IP'))
SERVER_PORT = int(os.getenv('DOOM_SERVER_PORT'))
MY_GUILD_ID = int(os.getenv('DEBUG_MY_GUILD_ID'))

# Bot initialization
intents = discord.Intents.default()
intents.message_content = True

bot_guild = discord.Object(id=MY_GUILD_ID)
bot_client = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot_client)
chat_webhook = discord.SyncWebhook.from_url(url=os.getenv('CHAT_WEBHOOK_URL'))

DOOMSERVER = ZandronumServer(SERVER_IP, SERVER_PORT)

CONFIG = {
    'info-channel-id': 0,
    'info-message-id': 0
}
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            CONFIG.update(json.load(f))
            print('Config loaded!')
    else:
        save_config()

def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=4)

@bot_client.event
async def on_ready():
    load_config()

    await tree.sync(guild=bot_guild)
    print('Guild commands synced')

    try:
        DOOMSERVER.start_rcon(os.getenv('RCON_PASSWORD'))
    except Exception as e:
        print(f'Failed to update doom server info: {e}')
    finally:
        DOOMSERVER.update_info()
    
    print('Bot started')
    
def generate_info_embed():
    embed = discord.Embed(title=f'{DOOMSERVER.name} ({SERVER_IP}:{SERVER_PORT})', colour=discord.Colour.brand_red(), timestamp=datetime.datetime.now())
    embed.add_field(name=f'Players', value=f'{DOOMSERVER.numplayers}/{DOOMSERVER.maxplayers}')
    embed.add_field(name=f'Map', value=f'{DOOMSERVER.mapname}')
    embed.add_field(name=f'IWAD', value=f'{DOOMSERVER.iwad}')
    embed.add_field(name=f'Mode', value=DOOMSERVER.gametype.name)
    embed.add_field(name=f'PWADs ({len(DOOMSERVER.pwads)})', value=', '.join(DOOMSERVER.pwads), inline=False)

    embed.set_footer(text=f'Zandronum {DOOMSERVER.version}')

    return embed

async def update_info():
    await bot_client.change_presence(activity=discord.Game(name=f'{DOOMSERVER.name} with {DOOMSERVER.numplayers} online'))

    channel_id = CONFIG['info-channel-id']

    if not channel_id:
        return
    
    channel = bot_client.get_channel(channel_id)

    message_id = CONFIG['info-message-id']

    embed = generate_info_embed()

    if message_id:
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed)

            return
        except discord.NotFound:
            pass

    msg = await channel.send(embed=embed)    

    CONFIG['info-message-id'] = msg.id
    save_config()

@tree.command(name = 'ping', description = 'Just for test', guild=bot_guild)
async def ping(ctx):
    await ctx.response.send_message("Pong!")

player_msg_re = re.compile(r'^(.*?)\:\s(.+)$')
system_msg_re = re.compile(r'^(->|.+\(RCON by .+\))')
ip_re = re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b')
connect_re = re.compile(r"^(?P<name>.+?) \([^)]*\) has connected\.$")
disconnect_re = re.compile(r"^client (?P<name>.+?) \([^)]*\) disconnected\.$")

def clean_nick(nick: str) -> str:
    return re.sub(r'\x1c\[[^\]]*\]|\x1c-', '', nick)

@DOOMSERVER.message
async def on_message(msg: str):
    if chat_webhook is None:
        return

    print(f'Processing RCon message: {msg}')

    m = connect_re.match(msg)
    if m:
        chat_webhook.send(content=f'**{clean_nick(m.group('name'))}** has connected', username='Server')

    m = disconnect_re.match(msg)
    if m:
        chat_webhook.send(content=f'**{clean_nick(m.group('name'))}** has disconnected', username='Server')
    
    RCON_KEYS = (
        "Name:", "Team:", "Skin:", "Gender:", "PlayerClass:", "Account:",
        "ColorSet:", "SwitchOnPickup:", "MoveBob:", "StillBob:",
        "Wi_NoAutostartMap:", "RailColor:", "Handicap:", "CL_TicsPerUpdate:",
        "CL_ConnectionType:", "CL_ClientFlags:", "Voice_Enable:",
        "Voice_ListenFilter:", "Voice_TransmitFilter:", "Autoaim:", "Color:",
        "Connect"
    )

    if ip_re.search(msg) or msg.strip().startswith(RCON_KEYS):
        return
    
    playermsg = player_msg_re.match(msg)
    systemmsg = system_msg_re.match(msg)

    if playermsg and not systemmsg:
        nick, message = playermsg.groups()

        if nick != '<Server>':
            chat_webhook.send(content=message, username=clean_nick(nick), avatar_url="https://sffempire.ru/bot/playeravatar.png")

@bot_client.event
async def on_message(message: discord.Message):
    if message.channel.id == int(os.getenv('CHAT_CHANNEL_ID')) and not message.author.bot:    
        DOOMSERVER.send_command_rcon(f'SAY "\\c[J1]{message.author.name}: \\c[C2]{message.content}"')

@DOOMSERVER.update
async def update(update: RConServerUpdate, value):
    match update:
        case RConServerUpdate.PLAYERDATA:
            print('Updated player data!')
            print(', '.join(value))
        
        case RConServerUpdate.ADMINCOUNT:
            print(f'New admin has connected! Admins: {value}')

        case RConServerUpdate.MAP:
            print(f'Map changed to {value}')
            chat_webhook.send(content=f'Map changed to **{value}**', username='Server')

    await update_info()


if __name__ == '__main__':
    try:
        bot_client.run(token=TOKEN)
    finally: 
        DOOMSERVER.disconnect_rcon()
