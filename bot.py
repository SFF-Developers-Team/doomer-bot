import os, json, discord, datetime
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

guild = discord.Object(id=MY_GUILD_ID)
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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

@client.event
async def on_ready():
    load_config()

    await tree.sync(guild=guild)
    print('guild passed')
    if DOOMSERVER.start_rcon(os.getenv('RCON_PASSWORD')):
        DOOMSERVER.update_info()

    print('Bot started')

@tasks.loop(seconds=10)
async def update_info():
    channel_id = CONFIG['info-channel-id']

    if not channel_id:
        return
    
    channel = client.get_channel(channel_id)

    message_id = CONFIG['info-message-id']

    if message_id:
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=generate_info_embed())

            return
        except discord.NotFound:
            pass

    msg = await channel.send(embed=generate_info_embed())    
    await client.change_presence(activity=discord.Game(name=f'{DOOMSERVER.name} with {DOOMSERVER.numplayers} online'))

    CONFIG['info-message-id'] = msg.id
    save_config()

@tree.command(name = 'ping', description = 'Just for test', guild=guild)
async def ping(ctx):
    await ctx.response.send_message("Pong!")
        
def generate_info_embed():
    embed = discord.Embed(title=f'{DOOMSERVER.name} ({SERVER_IP}:{SERVER_PORT})', colour=discord.Colour.brand_red(), timestamp=datetime.datetime.now())
    embed.add_field(name=f'Players', value=f'{DOOMSERVER.numplayers}/{DOOMSERVER.maxplayers}')
    embed.add_field(name=f'Map', value=f'{DOOMSERVER.mapname}')
    embed.add_field(name=f'IWAD', value=f'{DOOMSERVER.iwad}')
    embed.add_field(name=f'Mode', value=DOOMSERVER.gametype.name)
    embed.add_field(name=f'PWADs ({len(DOOMSERVER.pwads)})', value=', '.join(DOOMSERVER.pwads), inline=False)

    embed.set_footer(text=f'Zandronum {DOOMSERVER.version}')

    return embed

@DOOMSERVER.message
async def on_message(msg: str):
    # TODO: Sort messages
    print(msg)
    channel = client.get_channel(1405159978892787732)

    await channel.send(msg)

@DOOMSERVER.update
async def update(update: RConServerUpdate, value):
    await update_info()
    match update:
        case RConServerUpdate.PLAYERDATA:
            print('Updated player data!')
            print(', '.join(value))
        
        case RConServerUpdate.ADMINCOUNT:
            print(f'New admin has connected! Admins: {value}')

        case RConServerUpdate.MAP:
            print(f'Map changed to {value}')


if __name__ == '__main__':
    asyncio.run(client.start(token=TOKEN))