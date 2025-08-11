import os
import discord
import socket
import time
import struct
from bytereader import ByteReader
from huffman import Huffman
from discord import app_commands
from dotenv import load_dotenv

load_dotenv()

# Bot settings
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = str(os.getenv('DOOM_SERVER_IP'))
SERVER_PORT = int(os.getenv('DOOM_SERVER_PORT'))
MY_GUILD_ID = int(os.getenv('DEBUG_MY_GUILD_ID'))

# SQF flags
SQF_NAME                = 0x00000001
SQF_URL                 = 0x00000002
SQF_EMAIL               = 0x00000004
SQF_MAPNAME             = 0x00000008
SQF_MAXCLIENTS          = 0x00000010
SQF_MAXPLAYERS          = 0x00000020
SQF_PWADS               = 0x00000040
SQF_GAMETYPE            = 0x00000080
SQF_GAMENAME            = 0x00000100
SQF_IWAD                = 0x00000200
SQF_FORCEPASSWORD       = 0x00000400
SQF_FORCEJOINPASSWORD   = 0x00000800
SQF_GAMESKILL           = 0x00001000
SQF_BOTSKILL            = 0x00002000
SQF_DMFLAGS             = 0x00004000
SQF_LIMITS              = 0x00010000
SQF_TEAMDAMAGE          = 0x00020000
SQF_TEAMSCORES          = 0x00040000  # DEPRECATED
SQF_NUMPLAYERS          = 0x00080000
SQF_PLAYERDATA          = 0x00100000
SQF_TEAMINFO_NUMBER     = 0x00200000
SQF_TEAMINFO_NAME       = 0x00400000
SQF_TEAMINFO_COLOR      = 0x00800000
SQF_TEAMINFO_SCORE      = 0x01000000
SQF_TESTING_SERVER      = 0x02000000
SQF_DATA_MD5SUM         = 0x04000000

SQF2_PWAD_HASHES        = 0x00000001
SQF2_COUNTRY            = 0x00000002
SQF2_GAMEMODE_NAME      = 0x00000004
SQF2_GAMEMODE_SHORTNAME = 0x00000008
SQF2_VOICECHAT          = 0x00000010

# Server status
SERVER_LAUNCHER_CHALLENGE           = 5660023
SERVER_LAUNCHER_IGNORING            = 5660024
SERVER_LAUNCHER_BANNED              = 5660025
SERVER_LAUNCHER_CHALLENGE_SEGMENTED = 5660032

# Bot initialization
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

guild = discord.Object(id=MY_GUILD_ID)

@client.event
async def on_ready():
    await tree.sync(guild=guild)
    print('Готов к труду и обороне!')

@tree.command(name = 'ping', description = 'Just for test', guild=guild)
async def ping(ctx):
    await ctx.response.send_message("Pong!")

@tree.command(name = 'serverinfo', description = 'Get doom server info', guild=guild)
async def serverinfo(ctx):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)

    try:
        challenge = struct.pack("<l", 199)
        flags = struct.pack("<l", SQF_MAPNAME | SQF_MAXPLAYERS | SQF_NUMPLAYERS)
        cur_time = struct.pack("<l", int(time.time()))

        sock.sendto(Huffman.encode(challenge + flags + cur_time), (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(2048)
        data = ByteReader(Huffman.decode(data))

        status = data.read_long()

        if status != SERVER_LAUNCHER_CHALLENGE:
            pass 

        send_time = data.read_long()
        version = data.read_string()
        flags = data.read_long()

        mapname = data.read_string()
        maxplayers = data.read_byte()
        numplayers = data.read_byte()

        await ctx.response.send_message(f'Map: {mapname}\nPlayers: {numplayers}/{maxplayers}')

    except Exception as e:
        print(f'/serverinfo error: {e}')
        await ctx.response.send_message("Sorry I am broken :(")

    finally:
        sock.close()

if __name__ == '__main__':
    try:
        client.run(TOKEN)
    except discord.LoginFailure:
        print('Failed to login! Please check your .env file')