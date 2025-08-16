import time
import socket
import struct
import hashlib
from enum import IntEnum, IntFlag
from huffman import Huffman
from bytereader import ByteReader
from dataclasses import dataclass, field
from typing import Tuple


RCON_PROTOCOL_VERSION = 4

# https://wiki.zandronum.com/Launcher_protocol#Query_flags
class ServerQueryFlags(IntFlag):
    NAME                = 0x00000001
    URL                 = 0x00000002
    EMAIL               = 0x00000004
    MAPNAME             = 0x00000008
    MAXCLIENTS          = 0x00000010
    MAXPLAYERS          = 0x00000020
    PWADS               = 0x00000040
    GAMETYPE            = 0x00000080
    GAMENAME            = 0x00000100
    IWAD                = 0x00000200
    FORCEPASSWORD       = 0x00000400
    FORCEJOINPASSWORD   = 0x00000800
    GAMESKILL           = 0x00001000
    BOTSKILL            = 0x00002000
    DMFLAGS             = 0x00004000
    LIMITS              = 0x00010000
    TEAMDAMAGE          = 0x00020000
    TEAMSCORES          = 0x00040000  # DEPRECATED
    NUMPLAYERS          = 0x00080000
    PLAYERDATA          = 0x00100000
    TEAMINFO_NUMBER     = 0x00200000
    TEAMINFO_NAME       = 0x00400000
    TEAMINFO_COLOR      = 0x00800000
    TEAMINFO_SCORE      = 0x01000000
    TESTING_SERVER      = 0x02000000
    DATA_MD5SUM         = 0x04000000
    ALL_DMFLAGS         = 0x08000000
    SECURITY_SETTINGS   = 0x10000000
    OPTIONAL_WADS       = 0x20000000
    DEH                 = 0x40000000
    EXTENDED_INFO       = 0x80000000

class ServerQueryFlags2(IntFlag):
    PWAD_HASHES        = 0x00000001
    COUNTRY            = 0x00000002
    GAMEMODE_NAME      = 0x00000004
    GAMEMODE_SHORTNAME = 0x00000008
    VOICECHAT          = 0x00000010

# https://wiki.zandronum.com/Launcher_protocol#Challenge_packet
class ServerLauncherResponse(IntEnum):
    CHALLENGE           = 5660023
    IGNORING            = 5660024
    BANNED              = 5660025
    CHALLENGE_SEGMENTED = 5660032

# https://wiki.zandronum.com/RCon_protocol#Message_headers
class RConServerHeaders(IntEnum):
    OLDPROTOCOL         = 32
    BANNED              = 33
    SALT                = 34
    LOGGEDIN            = 35
    INVALIDPASSWORD     = 36
    MESSAGE             = 37
    UPDATE              = 38
    TABCOMPLETE         = 39
    TOOMANYTABCOMPLETES = 40

class RConServerUpdate(IntEnum):
    PLAYERDATA  = 0
    ADMINCOUNT  = 1
    MAP         = 2

class RConClientHeaders(IntEnum):
    BEGINCONNECTION = 52
    PASSWORD        = 53
    COMMAND         = 54
    PONG            = 55
    DISCONNECT      = 56
    TABCOMPLETE     = 57

# https://wiki.zandronum.com/Launcher_protocol#Game_modes 
class ZandronumGamemode(IntEnum):
    COOPERATIVE     = 0
    SURVIVAL        = 1
    INVASION        = 2
    DEATHMATCH      = 3
    TEAMPLAY        = 4
    DUEL            = 5
    TERMINATOR      = 6
    LASTMANSTANDING = 7
    TEAMLMS         = 8
    POSSESSION      = 9
    TEAMPOSSESSION  = 10
    TEAMGAME        = 11
    CTF             = 12
    ONEFLAGCTF      = 13
    SKULLTAG        = 14
    DOMINATION      = 15

@dataclass
class ZandronumTeam:
    name: str
    color: Tuple[int, int, int, int] = field(default=(255, 255, 255, 255))
    score: int = 0

    def __post_init__(self):
        if not all(0 <= c <= 255 for c in self.color):
            raise ValueError('Each color component must be between 0 and 255')
        if self.score < 0:
            raise ValueError('Score cannot be negative')

    def set_color(self, r: int, g: int, b: int, a: int = 255):
        if not all(0 <= c <= 255 for c in (r, g, b, a)):
            raise ValueError('Each color component must be between 0 and 255')
        self.color = (r, g, b, a)

    def __str__(self):
        return f'Team \"{self.name}\" | Score: {self.score} | Color: {self.color}'

@dataclass
class ZandronumPlayer:
    name: str
    frags: int = 0
    ping: int = 0
    spectating: bool = False
    bot: bool = False
    team: int = -1
    time: int = 0 # in minutes

class ZandronumServer:
    def __init__(self, hostname: str, port: int):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(5) # 5 seconds
        self._hostname = hostname
        self._port = port

        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Initialize all attributes
        self.version = ''
        self.name = ''
        self.url = ''
        self.email = ''
        self.mapname = ''
        self.maxclients = 0
        self.maxplayers = 0
        self.pwads = []
        self.gametype = ZandronumGamemode.COOPERATIVE
        self.instagib = False
        self.buckshot = False
        self.gamename = ''
        self.iwad = ''
        self.forcepassword = False
        self.forcejoinpassword = False
        self.skill = 0
        self.botskill = 0
        self.dmflags = 0
        self.dmflags2 = 0
        self.zadmflags = 0
        self.compatflags = 0
        self.zacompatflags = 0
        self.compatflags2 = 0
        self.numplayers = 0
        self.players = []
        self.fraglimit = 0
        self.timelimit = 0
        self.timeleft = 0
        self.duellimit = 0
        self.pointlimit = 0
        self.winlimit = 0
        self.teamdamage = 0.0
        self.numteams = 0
        self.teams = []
        self.testing = False
        self.deh = []
    
    def __del__(self):
        self._sock.close()

    def _send(self, data: bytes) -> int:
        return self._sock.sendto(Huffman.encode(data), (self._hostname, self._port))

    def _recv(self, bufsize: int) -> ByteReader:
        try:
            data, _ = self._sock.recvfrom(bufsize)
        except socket.timeout:
            raise TimeoutError('Connection timed out while waiting for response from server.')
        except socket.error as e:
            raise ConnectionError(f'Could not receive data from server. Error: {e}')

        return ByteReader(Huffman.decode(data))

    def update_info(self, flags: ServerQueryFlags = 0xFFFFFFFF) -> ServerQueryFlags:
        cur_time = int(time.time())
        
        self._send(struct.pack("<lLl", 199, flags, cur_time))

        res = self._recv(1024)

        if res.remaining() < 4:
            raise ValueError("Received empty response")
    
        status = res.read_long()

        # UNTESTED CODE
        if status == ServerLauncherResponse.CHALLENGE_SEGMENTED:
            segments = {}

            while True:
                seg_number = res.read_byte()
                seg_total = res.read_byte()
                offset = res.read_short()
                size = res.read_short()
                total = res.read_short()

                segments[seg_number] = res.read_bytes(size)

                if len(segments) == seg_total:
                    res = b''.join(segments[i] for i in sorted(segments))
                    break
                
                res, _ = self._sock.recvfrom(1024)
                res = ByteReader(Huffman.decode(res))
                status = res.read_long()

                if status != ServerLauncherResponse.CHALLENGE_SEGMENTED:
                    raise ValueError("Unexpected packet")
        
        if status == ServerLauncherResponse.BANNED:
            raise ConnectionRefusedError('Server banned you.')
    
        if status == ServerLauncherResponse.IGNORING:
            raise ConnectionRefusedError('Server ignoring you.')

        send_time = res.read_ulong()

        self.version = res.read_string()
        res_flags = res.read_long()

        if res_flags & ServerQueryFlags.NAME:
            self.name = res.read_string()
        
        if res_flags & ServerQueryFlags.URL:
            self.url = res.read_string()

        if res_flags & ServerQueryFlags.EMAIL:
            self.email = res.read_string()
        
        if res_flags & ServerQueryFlags.MAPNAME:
            self.mapname = res.read_string()
        
        if res_flags & ServerQueryFlags.MAXCLIENTS:
            self.maxclients = res.read_byte()

        if res_flags & ServerQueryFlags.MAXPLAYERS:
            self.maxplayers = res.read_byte()

        if res_flags & ServerQueryFlags.PWADS:
            n = res.read_byte()
            self.pwads.clear()

            for i in range(n):
                self.pwads.append(res.read_string())
        
        if res_flags & ServerQueryFlags.GAMETYPE:
            self.gametype = ZandronumGamemode(res.read_byte())
            self.instagib = res.read_byte()
            self.buckshot = res.read_byte()
        
        if res_flags & ServerQueryFlags.GAMENAME:
            self.gamename = res.read_string()

        if res_flags & ServerQueryFlags.IWAD:
            self.iwad = res.read_string()

        if res_flags & ServerQueryFlags.FORCEPASSWORD:
            self.forcepassword = res.read_byte()

        if res_flags & ServerQueryFlags.FORCEJOINPASSWORD:
            self.forcejoinpassword = res.read_byte()

        if res_flags & ServerQueryFlags.GAMESKILL:
            self.skill = res.read_byte()

        if res_flags & ServerQueryFlags.BOTSKILL:
            self.skill = res.read_byte()

        if res_flags & ServerQueryFlags.DMFLAGS:
            self.dmflags = res.read_long()
            self.dmflags2 = res.read_long()
            self.compatflags = res.read_long()
        
        if res_flags & ServerQueryFlags.LIMITS:
            self.fraglimit = res.read_short()
            self.timelimit = res.read_short()
            
            if self.timelimit > 0:
                self.timeleft = res.read_short()

            self.duellimit = res.read_short()
            self.pointlimit = res.read_short()
            self.winlimit = res.read_short()

        if res_flags & ServerQueryFlags.TEAMDAMAGE:
            self.teamdamage = res.read_float()

        if res_flags & ServerQueryFlags.TEAMSCORES:
            res.read_short()
            res.read_short()

        if res_flags & ServerQueryFlags.NUMPLAYERS:
            self.numplayers = res.read_byte()

        if res_flags & ServerQueryFlags.PLAYERDATA:
            self.players.clear()

            for i in range(self.numplayers):
                player = ZandronumPlayer()
                player.name = res.read_string()
                player.frags = res.read_short()
                player.ping = res.read_short()
                player.spectating = res.read_byte()
                player.bot = res.read_byte()
                player.team = res.read_byte()
                player.time = res.read_byte()

                self.players.append(player)
        
        if res_flags & ServerQueryFlags.TEAMINFO_NUMBER:
            self.numteams = res.read_byte()

        if res_flags & ServerQueryFlags.TEAMINFO_NAME:
            for i in range(self.numteams):
                self.teams[i].name = res.read_string()

        if res_flags & ServerQueryFlags.TEAMINFO_COLOR:
            for i in range(self.numteams):
                self.teams[i].color = struct.unpack("<BBBB", res.read_long())
        
        if res_flags & ServerQueryFlags.TEAMINFO_NAME:
            for i in range(self.numteams):
                self.teams[i].name = res.read_short()

        if res_flags & ServerQueryFlags.TESTING_SERVER:
            self.testing = res.read_byte()
            res.read_string()

        if res_flags & ServerQueryFlags.ALL_DMFLAGS:
            n = res.read_byte()

            if n > 0:
                self.dmflags = res.read_long()
            if n > 1:
                self.dmflags2 = res.read_long()
            if n > 3:
                self.zadmflags = res.read_long()
            if n > 4:
                self.compatflags = res.read_long()
            if n > 5:
                self.zacompatflags = res.read_long()
            if n > 6:
                self.compatflags2 = res.read_long()

        return res_flags

    def login_rcon(self, password: str):
        self._send(struct.pack('<BB', RConClientHeaders.BEGINCONNECTION, RCON_PROTOCOL_VERSION))

        res = self._recv(64)
        status = res.read_byte()

        if status == RConServerHeaders.BANNED:
            raise ConnectionRefusedError('You\'re banned by this server!')
            
        if status == RConServerHeaders.OLDPROTOCOL:
            serverproto = res.read_byte()
            serverversion = res.read_string()

            raise ConnectionRefusedError(
                f'Protocol version ({RCON_PROTOCOL_VERSION}) is too old!',
                f'Server protocol: {serverproto}. Server version: {serverversion}.'
            )

        if status != RConServerHeaders.SALT:
            raise ValueError('Unexpected RCon packet!')

        salt = res.read_bytes(32)
        hash = hashlib.md5(salt + password.encode()).hexdigest()

        self._send(struct.pack('<B', RConClientHeaders.PASSWORD) + hash.encode())
        res = self._recv(256)

        status = res.read_byte()

        if status == RConServerHeaders.INVALIDPASSWORD:
            raise ConnectionRefusedError('Invalid RCon password!')

        if status != RConServerHeaders.LOGGEDIN:
            raise ValueError('Unexpected RCon packet!')