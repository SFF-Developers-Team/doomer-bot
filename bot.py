import os
import discord
import socket
import time
import struct
from bytereader import ByteReader
from huffman import Huffman
from discord import *
from dotenv import load_dotenv
import asyncio
import schedule

load_dotenv()

# Bot settings
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = str(os.getenv('DOOM_SERVER_IP'))
SERVER_PORT = int(os.getenv('DOOM_SERVER_PORT'))
MY_GUILD_ID = int(os.getenv('DEBUG_MY_GUILD_ID'))
SERVER_INFO_CHANNEL = int(os.getenv('SERVER_INFO_CHANNEL'))

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

# Gamemodes (0-15), check https://wiki.zandronum.com/Launcher_protocol#Game_modes 
gamemodes = [ 'Cooperative', 'Survival', 'Invasion', 'Deathmatch', 'TeamPlay', 'Duel', 'Terminator', 'LastManStanding', 'TeamLMS', 'Possession', 
             'TeamPossession', 'TeamGame', 'CTF', 'OneFlagCTF', 'SkullTag', 'Domintation']

# Bot initialization
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

guild = discord.Object(id=MY_GUILD_ID)

@client.event
async def on_ready():
    await tree.sync(guild=guild)
    await serverinfo()
    print('Bot started')

@tree.command(name = 'ping', description = 'Just for test', guild=guild)
async def ping(ctx):
    await ctx.response.send_message("Pong!")
    
async def updateinfo():
    schedule.every(5).seconds.do(serverinfo)
    while True:
        schedule.run_pending()
        time.sleep(1)
    
async def serverinfo():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)

    try:
        challenge = struct.pack("<l", 199)
        flags = struct.pack("<l", SQF_NAME | SQF_MAPNAME | SQF_MAXPLAYERS | SQF_PWADS | SQF_GAMETYPE | SQF_IWAD | SQF_NUMPLAYERS )
        cur_time = struct.pack("<l", int(time.time()))

        sock.sendto(Huffman.encode(challenge + flags + cur_time), (SERVER_IP, SERVER_PORT))
        data, _ = sock.recvfrom(2048)
        data = ByteReader(Huffman.decode(data))

        status = data.read_long()

        if status != SERVER_LAUNCHER_CHALLENGE:
            pass 
        
        # Reading info from packets, check https://wiki.zandronum.com/Launcher_protocol#Packet_contents
        send_time = data.read_long()
        version = data.read_string()
        flags = data.read_long()
        versionZand = ""
        i = 0
        # Version <1.0 not working, but why u used it?
        # Also i think it method sucks, pls rewrite it if this really bad
        while version[i] == "3" or version[i] == "2" or version[i] == "1" or version[i] == "0" or version[i] == ".": 
            print(version[i])
            versionZand += version[i]
            i += 1
        servername = data.read_string()
        mapname = data.read_string()
        maxplayers = data.read_byte()
        pwadsnum = data.read_byte()
        pwads = ""
        for i in range(pwadsnum):
            # Creating string with pwads
            pwads += data.read_string()
            if i >= 0 and i != pwadsnum - 1:
                pwads += (", ")
        gametype = data.read_byte()
        gametypeinsta = data.read_byte()
        gametypebuckshot = data.read_byte()
        iwads = data.read_string()
        numplayers = data.read_byte()
        
        # Creating embeded and sending it
        embed = discord.Embed(url="", title=f'{servername} Info', colour=discord.Colour.brand_red())
        embed.add_field(name=f'Address: {SERVER_IP}:{SERVER_PORT}', value="", inline=False)
        embed.add_field(name=f'Players: {numplayers}/{maxplayers}', value="", inline=False)
        embed.add_field(name=f'Mapname: {mapname}', value="", inline=False)
        embed.add_field(name=f'IWADs: {iwads}', value="", inline=False)
        embed.add_field(name=f'PWADs: {pwads}', value="", inline=False)
        embed.add_field(name=f'Game Type: {gamemodes[gametype]}', value="", inline=False)
        embed.set_footer(text = f'Zandronum version: {versionZand}')
        
        await client.change_presence(status=discord.Status.online, activity=discord.Activity(name=f"{servername} with {numplayers} players online", type=discord.ActivityType.playing))
        print(version)
        if os.path.isfile("serverinfo.txt"):
            channel = client.get_channel(SERVER_INFO_CHANNEL)       
            # Getting id of message with serverinfo
            idfile = open("serverinfo.txt")
            id = idfile.read()
            msg = channel.get_partial_message(id)
            await msg.edit(embed=embed)
        else:
            # If it doesnt exists, we creating new message and write id in a file
            channel = client.get_channel(SERVER_INFO_CHANNEL)       
            idfile = open("serverinfo.txt", "x") 
            msg = await channel.send(embed=embed)
            idfile.write(str(msg.id))
        print(msg.id)
    except Exception as e:

        print(f'/serverinfo error: {e}')
        await channel.send("Sorry i am broken :(")

    finally:
        sock.close()
if __name__ == '__main__':
    # TODO: Make update info about server every n minute
    client.run(token=TOKEN)
